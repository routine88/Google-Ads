#!/usr/bin/env python3
"""Core analytics helpers for the Google Ads AI agent (GUI + future CLI).

Features:
* Runs GAQL queries for hourly, search term, placement, and campaign data.
* Flags first-hour click spikes (earliest hour with traffic) and suggests mitigations.
* Surfaces high-spend search terms or placements with zero conversions.
* Prepares campaign summary tables for downstream presentation layers.

All logic here is read-only, making it safe to reuse in GUI apps or scheduled jobs.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.protobuf.json_format import MessageToDict


GAQL_HOURLY = """
SELECT
  customer.id,
  segments.date,
  segments.hour,
  metrics.clicks,
  metrics.impressions,
  metrics.ctr,
  metrics.conversions,
  metrics.cost_micros
FROM customer
WHERE segments.date BETWEEN '{start}' AND '{end}'
"""

GAQL_SEARCH_TERMS = """
SELECT
  customer.id,
  campaign.id,
  campaign.name,
  ad_group.id,
  segments.search_term,
  metrics.clicks,
  metrics.impressions,
  metrics.ctr,
  metrics.conversions,
  metrics.cost_micros
FROM search_term_view
WHERE segments.date BETWEEN '{start}' AND '{end}'
  AND metrics.impressions > 0
"""

GAQL_PLACEMENTS = """
SELECT
  customer.id,
  campaign.id,
  campaign.name,
  ad_group.id,
  detail_placement_view.display_name,
  detail_placement_view.group_placement_target_url,
  metrics.impressions,
  metrics.clicks,
  metrics.ctr,
  metrics.conversions,
  metrics.cost_micros
FROM detail_placement_view
WHERE segments.date BETWEEN '{start}' AND '{end}'
  AND metrics.impressions > 0
"""

GAQL_CAMPAIGNS = """
SELECT
  campaign.id,
  campaign.name,
  campaign.status,
  campaign.advertising_channel_type,
  metrics.impressions,
  metrics.clicks,
  metrics.ctr,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value
FROM campaign
WHERE segments.date BETWEEN '{start}' AND '{end}'
"""


def run_query(client: GoogleAdsClient, customer_id: str, gaql: str):
    ga_service = client.get_service("GoogleAdsService")
    response = ga_service.search(customer_id=customer_id, query=gaql)
    return [row for row in response]


def flatten_message(message: Dict, parent_key: str = "") -> Dict:
    flat = {}
    for key, value in message.items():
        new_key = f"{parent_key}.{key}" if parent_key else key
        if isinstance(value, dict):
            flat.update(flatten_message(value, new_key))
        elif isinstance(value, list):
            flat[new_key] = ",".join(map(str, value))
        else:
            flat[new_key] = value
    return flat


def df_from_rows(rows: Iterable) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    dicts = []
    for row in rows:
        proto = MessageToDict(row._pb, preserving_proto_field_name=True)
        dicts.append(flatten_message(proto))
    return pd.DataFrame(dicts)


def micros_to_currency(value) -> float:
    try:
        return float(value) / 1_000_000.0
    except (ValueError, TypeError):
        return np.nan


def analyze_hourly(
    df_hour: pd.DataFrame,
    min_clicks: int = 50,
    spike_ratio_threshold: float = 2.5,
) -> Dict:
    if df_hour.empty or "segments.hour" not in df_hour.columns:
        return {"insight": "No hourly data returned."}

    for col in [
        "metrics.clicks",
        "metrics.impressions",
        "metrics.conversions",
        "metrics.cost_micros",
        "segments.hour",
    ]:
        if col in df_hour.columns:
            df_hour[col] = pd.to_numeric(df_hour[col], errors="coerce")

    grouped = (
        df_hour.groupby("segments.hour")
        .agg(
            {
                "metrics.clicks": "sum",
                "metrics.impressions": "sum",
                "metrics.conversions": "sum",
                "metrics.cost_micros": "sum",
            }
        )
        .reset_index()
        .sort_values("segments.hour")
    )
    grouped["cost"] = grouped["metrics.cost_micros"].apply(micros_to_currency)
    grouped["ctr"] = (
        grouped["metrics.clicks"] / grouped["metrics.impressions"]
    ).replace([np.inf, -np.inf], np.nan)
    grouped["cvr"] = (
        grouped["metrics.conversions"] / grouped["metrics.clicks"]
    ).replace([np.inf, -np.inf], np.nan)

    active_hours = grouped.loc[grouped["metrics.clicks"] > 0, "segments.hour"]
    first_active_hour = int(active_hours.min()) if not active_hours.empty else 0
    first_hour_clicks = grouped.loc[
        grouped["segments.hour"] == first_active_hour, "metrics.clicks"
    ].sum()

    rest_clicks = grouped.loc[
        grouped["segments.hour"] != first_active_hour, "metrics.clicks"
    ]
    rest_median = rest_clicks.median() if not rest_clicks.empty else np.nan

    spike_ratio = (
        float(first_hour_clicks) / float(rest_median)
        if rest_median and rest_median > 0
        else np.nan
    )

    insight = {
        "first_active_hour": first_active_hour,
        "first_hour_clicks": int(first_hour_clicks),
        "rest_median_clicks": float(rest_median)
        if rest_median == rest_median
        else None,
        "spike_ratio": float(spike_ratio)
        if spike_ratio == spike_ratio
        else None,
    }

    actions: List[str] = []
    if (
        spike_ratio
        and spike_ratio >= spike_ratio_threshold
        and first_hour_clicks >= min_clicks
    ):
        local_hour = first_active_hour
        actions.append(
            f"Clicks at hour {local_hour}:00 are {spike_ratio:.1f}x the median of other hours "
            "— consider testing stricter start times, bid modifiers, or temporarily pausing that block."
        )
        actions.append(
            "Enable/verify click-fraud protection and tighten geo targeting for the impacted campaigns."
        )

    return {"hourly_table": grouped, "insight": insight, "actions": actions}


def analyze_search_terms(df_st: pd.DataFrame) -> Dict:
    if df_st.empty or "metrics.clicks" not in df_st.columns:
        return {"insight": "No search term data returned."}

    for col in [
        "metrics.clicks",
        "metrics.impressions",
        "metrics.conversions",
        "metrics.cost_micros",
    ]:
        if col in df_st.columns:
            df_st[col] = pd.to_numeric(df_st[col], errors="coerce")

    df_st["cost"] = df_st["metrics.cost_micros"].apply(micros_to_currency)
    losers = df_st[
        (df_st["metrics.clicks"] >= 20)
        & (df_st["metrics.conversions"] == 0)
        & (df_st["cost"] >= 10.0)
    ].copy()
    losers = losers.sort_values("cost", ascending=False).head(25)

    recs = []
    for _, row in losers.iterrows():
        recs.append(
            {
                "search_term": row.get("segments.search_term"),
                "campaign": row.get("campaign.name"),
                "reason": "High spend/clicks with zero conversions — consider adding as a negative keyword.",
                "est_cost": float(row.get("cost", 0.0)),
            }
        )
    return {"negatives": recs}


def analyze_placements(df_pl: pd.DataFrame) -> Dict:
    if df_pl.empty or "metrics.clicks" not in df_pl.columns:
        return {"insight": "No placement data returned."}

    for col in [
        "metrics.clicks",
        "metrics.impressions",
        "metrics.conversions",
        "metrics.cost_micros",
    ]:
        if col in df_pl.columns:
            df_pl[col] = pd.to_numeric(df_pl[col], errors="coerce")

    df_pl["cost"] = df_pl["metrics.cost_micros"].apply(micros_to_currency)
    losers = df_pl[
        (df_pl["metrics.clicks"] >= 15)
        & (df_pl["metrics.conversions"] == 0)
        & (df_pl["cost"] >= 8.0)
    ].copy()
    losers = losers.sort_values("cost", ascending=False).head(25)

    recs = []
    for _, row in losers.iterrows():
        placement = row.get("detail_placement_view.group_placement_target_url") or row.get(
            "detail_placement_view.display_name"
        )
        recs.append(
            {
                "placement": placement,
                "campaign": row.get("campaign.name"),
                "reason": "High spend/clicks with zero conversions — consider excluding this placement.",
                "est_cost": float(row.get("cost", 0.0)),
            }
        )
    return {"exclusions": recs}


def prepare_campaign_summary(df_c: pd.DataFrame) -> pd.DataFrame:
    if df_c.empty:
        return df_c

    numeric_cols = [
        "metrics.impressions",
        "metrics.clicks",
        "metrics.ctr",
        "metrics.conversions",
        "metrics.cost_micros",
        "metrics.conversions_value",
    ]
    for col in numeric_cols:
        if col in df_c.columns:
            df_c[col] = pd.to_numeric(df_c[col], errors="coerce")
    df_c["cost"] = df_c["metrics.cost_micros"].apply(micros_to_currency)
    return df_c.sort_values("cost", ascending=False)


def analyze_account(
    client,
    customer_id: str,
    start_date: date,
    end_date: date,
    min_first_hour_clicks: int = 50,
    spike_ratio_threshold: float = 2.5,
) -> Dict:
    customer = customer_id.replace("-", "")

    rows_hour = run_query(client, customer, GAQL_HOURLY.format(start=start_date, end=end_date))
    df_hour = df_from_rows(rows_hour)
    hourly = analyze_hourly(
        df_hour,
        min_clicks=min_first_hour_clicks,
        spike_ratio_threshold=spike_ratio_threshold,
    )

    rows_st = run_query(client, customer, GAQL_SEARCH_TERMS.format(start=start_date, end=end_date))
    df_st = df_from_rows(rows_st)
    search_term_findings = analyze_search_terms(df_st)

    rows_pl = run_query(client, customer, GAQL_PLACEMENTS.format(start=start_date, end=end_date))
    df_pl = df_from_rows(rows_pl)
    placement_findings = analyze_placements(df_pl)

    rows_campaigns = run_query(client, customer, GAQL_CAMPAIGNS.format(start=start_date, end=end_date))
    df_campaigns = df_from_rows(rows_campaigns)
    campaign_summary = prepare_campaign_summary(df_campaigns)

    return {
        "hourly": hourly,
        "search_terms": search_term_findings,
        "placements": placement_findings,
        "campaigns": campaign_summary,
    }
