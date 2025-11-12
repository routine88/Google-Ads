#!/usr/bin/env python3
"""Tkinter GUI for the Google Ads AI Agent."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import google.auth.transport.requests
import pandas as pd
from google.ads.googleads.client import GoogleAdsClient
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ads_agent import analyze_account
from config_manager import load_settings, save_settings

SCOPES = ["https://www.googleapis.com/auth/adwords"]
TOKEN_PATH = Path("token.json")


class GoogleAdsApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Google Ads AI Agent")
        self.geometry("1200x780")
        self.minsize(1000, 720)

        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.style.configure("TFrame", background="#f6f6f6")
        self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
        self.style.configure("Subheading.TLabel", font=("Segoe UI", 11, "bold"))

        self.settings = load_settings()

        self.client_secret_var = tk.StringVar(value=self.settings.get("client_secret_path"))
        self.developer_token_var = tk.StringVar(value=self.settings.get("developer_token"))
        self.login_customer_var = tk.StringVar(value=self.settings.get("login_customer_id"))
        self.customer_id_var = tk.StringVar(value=self.settings.get("customer_id"))
        self.lookback_var = tk.IntVar(value=int(self.settings.get("lookback_days", 7)))
        self.first_hour_clicks_var = tk.IntVar(
            value=int(self.settings.get("min_first_hour_clicks", 50))
        )
        self.spike_ratio_var = tk.DoubleVar(value=float(self.settings.get("spike_ratio", 2.5)))
        self.status_var = tk.StringVar(value="Waiting for sign-in.")
        self.hourly_insight_var = tk.StringVar(
            value="Run analysis to view hourly spike diagnostics."
        )

        self.credentials: Credentials | None = None

        self._build_layout()
        self._load_cached_credentials()

    # Layout -----------------------------------------------------------------
    def _build_layout(self) -> None:
        header = ttk.Frame(self, padding=(20, 15))
        header.pack(fill="x")
        ttk.Label(header, text="Google Ads AI Agent Dashboard", style="Header.TLabel").pack(
            side="left"
        )
        ttk.Label(header, textvariable=self.status_var).pack(side="right")

        controls = ttk.Frame(self, padding=(20, 10))
        controls.pack(fill="x")
        self._build_controls(controls)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.summary_tab = ttk.Frame(self.notebook, padding=15)
        self.search_tab = ttk.Frame(self.notebook, padding=15)
        self.placement_tab = ttk.Frame(self.notebook, padding=15)
        self.campaign_tab = ttk.Frame(self.notebook, padding=15)
        self.logs_tab = ttk.Frame(self.notebook, padding=15)

        self.notebook.add(self.summary_tab, text="Hourly Summary")
        self.notebook.add(self.search_tab, text="Search Terms")
        self.notebook.add(self.placement_tab, text="Placements")
        self.notebook.add(self.campaign_tab, text="Campaigns")
        self.notebook.add(self.logs_tab, text="Logs")

        self._build_summary_tab()
        self._build_search_tab()
        self._build_placement_tab()
        self._build_campaign_tab()
        self._build_logs_tab()

    def _build_controls(self, parent: ttk.Frame) -> None:
        grid_opts = {"padx": 5, "pady": 5, "sticky": "ew"}
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)

        ttk.Label(parent, text="Client secret JSON").grid(row=0, column=0, **grid_opts)
        client_entry = ttk.Entry(parent, textvariable=self.client_secret_var)
        client_entry.grid(row=1, column=0, **grid_opts)
        ttk.Button(parent, text="Browse…", command=self._select_client_secret).grid(
            row=1, column=1, **grid_opts
        )

        ttk.Label(parent, text="Developer token").grid(row=0, column=2, **grid_opts)
        ttk.Entry(parent, textvariable=self.developer_token_var).grid(row=1, column=2, **grid_opts)

        ttk.Label(parent, text="Login customer ID (MCC, optional)").grid(row=2, column=0, **grid_opts)
        ttk.Entry(parent, textvariable=self.login_customer_var).grid(row=3, column=0, **grid_opts)

        ttk.Label(parent, text="Customer ID to analyze").grid(row=2, column=1, **grid_opts)
        ttk.Entry(parent, textvariable=self.customer_id_var).grid(row=3, column=1, **grid_opts)

        ttk.Label(parent, text="Lookback days").grid(row=2, column=2, **grid_opts)
        ttk.Spinbox(parent, from_=1, to=90, textvariable=self.lookback_var).grid(
            row=3, column=2, **grid_opts
        )

        ttk.Label(parent, text="Min hour-0 clicks").grid(row=4, column=0, **grid_opts)
        ttk.Spinbox(parent, from_=10, to=500, increment=5, textvariable=self.first_hour_clicks_var).grid(
            row=5, column=0, **grid_opts
        )

        ttk.Label(parent, text="Spike ratio threshold").grid(row=4, column=1, **grid_opts)
        ttk.Spinbox(parent, from_=1.0, to=10.0, increment=0.1, textvariable=self.spike_ratio_var).grid(
            row=5, column=1, **grid_opts
        )

        button_frame = ttk.Frame(parent)
        button_frame.grid(row=4, column=2, rowspan=2, **grid_opts)

        self.save_btn = ttk.Button(button_frame, text="Save Settings", command=self._save_settings)
        self.save_btn.pack(fill="x", pady=(0, 6))

        self.sign_in_btn = ttk.Button(button_frame, text="Sign in with Google", command=self.start_oauth)
        self.sign_in_btn.pack(fill="x", pady=(0, 6))
        self.run_btn = ttk.Button(
            button_frame, text="Run Analysis", command=self.start_analysis, state="disabled"
        )
        self.run_btn.pack(fill="x")

    def _build_summary_tab(self) -> None:
        ttk.Label(self.summary_tab, textvariable=self.hourly_insight_var, style="Subheading.TLabel").pack(
            anchor="w", pady=(0, 10)
        )

        columns = ("Hour", "Clicks", "Impressions", "Conversions", "CTR", "CVR", "Cost ($)")
        self.hourly_tree = self._create_tree(self.summary_tab, columns)

        self.actions_box = tk.Text(self.summary_tab, height=4, state="disabled", wrap="word")
        self.actions_box.pack(fill="both", expand=False, pady=(10, 0))
        self._write_actions([])

    def _build_search_tab(self) -> None:
        columns = ("Search Term", "Campaign", "Reason", "Est. Cost ($)")
        self.search_tree = self._create_tree(self.search_tab, columns)

    def _build_placement_tab(self) -> None:
        columns = ("Placement", "Campaign", "Reason", "Est. Cost ($)")
        self.placement_tree = self._create_tree(self.placement_tab, columns)

    def _build_campaign_tab(self) -> None:
        columns = ("Campaign ID", "Name", "Cost ($)", "Conversions", "CTR", "Clicks", "Impressions")
        self.campaign_tree = self._create_tree(self.campaign_tab, columns)

    def _build_logs_tab(self) -> None:
        self.log_text = tk.Text(self.logs_tab, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)

    def _create_tree(self, parent: ttk.Frame, columns: tuple[str, ...]) -> ttk.Treeview:
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)
        tree = ttk.Treeview(container, columns=columns, show="headings", height=10)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor="center")
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    # Credential handling ----------------------------------------------------
    def _select_client_secret(self) -> None:
        path = filedialog.askopenfilename(
            title="Select OAuth client secret",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.client_secret_var.set(path)
            self._save_settings()

    def _load_cached_credentials(self) -> None:
        if not TOKEN_PATH.exists():
            return
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), scopes=SCOPES)
            if creds and creds.valid:
                self.credentials = creds
                self.status_var.set("Using cached OAuth credentials.")
                self.run_btn.configure(state="normal")
            elif creds and creds.expired and creds.refresh_token:
                self._refresh_credentials(creds)
        except Exception as exc:  # noqa: BLE001
            self._log(f"Failed to load cached credentials: {exc}")

    def _refresh_credentials(self, creds: Credentials) -> None:
        try:
            request = google.auth.transport.requests.Request()
            creds.refresh(request)
            TOKEN_PATH.write_text(creds.to_json())
            self.credentials = creds
            self.after(0, lambda: self._set_status("Credentials refreshed."))
            self.after(0, lambda: self.run_btn.configure(state="normal"))
        except Exception as exc:  # noqa: BLE001
            self.after(0, lambda: self._log(f"Failed to refresh credentials: {exc}"))

    def start_oauth(self) -> None:
        client_secret_path = Path(self.client_secret_var.get()).expanduser()
        if not client_secret_path.exists():
            messagebox.showerror("Missing file", f"{client_secret_path} was not found.")
            return

        def _oauth_flow() -> None:
            self.after(0, lambda: self._set_status("Launching browser for OAuth…"))
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(client_secret_path), scopes=SCOPES
                )
                creds = flow.run_local_server(port=0)
                TOKEN_PATH.write_text(creds.to_json())
                self.credentials = creds
                self.after(0, lambda: self._set_status("Signed in successfully."))
                self.after(0, lambda: self._log("OAuth flow completed."))
                self.after(0, lambda: self.run_btn.configure(state="normal"))
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                self.after(0, lambda: self._set_status("OAuth failed."))
                self.after(0, lambda msg=message: self._show_error_dialog("OAuth failed", msg))
                self.after(0, lambda msg=message: self._log(f"OAuth error: {msg}"))

        threading.Thread(target=_oauth_flow, daemon=True).start()

    # Analysis ---------------------------------------------------------------
    def start_analysis(self) -> None:
        if not self.credentials:
            messagebox.showwarning("Sign in required", "Please sign in with Google first.")
            return
        if not self.developer_token_var.get().strip():
            messagebox.showwarning("Developer token required", "Enter your developer token.")
            return
        if not self.customer_id_var.get().strip():
            messagebox.showwarning("Customer ID required", "Enter a customer ID to analyze.")
            return

        self._save_settings()
        self.run_btn.configure(state="disabled")
        self._set_status("Running analysis…")

        def _analysis() -> None:
            try:
                client = self._build_client()
                lookback = max(1, int(self.lookback_var.get()))
                end_date = datetime.now(timezone.utc).date()
                start_date = end_date - timedelta(days=lookback)
                result = analyze_account(
                    client,
                    self.customer_id_var.get(),
                    start_date,
                    end_date,
                    min_first_hour_clicks=int(self.first_hour_clicks_var.get()),
                    spike_ratio_threshold=float(self.spike_ratio_var.get()),
                )
                self.after(
                    0,
                    lambda: self._render_results(result, lookback, start_date, end_date),
                )
                self.after(0, lambda: self._log("Analysis completed successfully."))
                self.after(0, lambda: self._set_status("Analysis ready."))
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                self.after(0, lambda msg=message: self._log(f"Analysis failed: {msg}"))
                self.after(0, lambda: self._set_status("Analysis failed."))
                self.after(0, lambda msg=message: self._show_error_dialog("Analysis error", msg))
            finally:
                self.after(0, lambda: self.run_btn.configure(state="normal"))

        threading.Thread(target=_analysis, daemon=True).start()

    def _build_client(self) -> GoogleAdsClient:
        if not self.credentials:
            raise ValueError("No OAuth credentials available.")
        if self.credentials.expired and self.credentials.refresh_token:
            self._refresh_credentials(self.credentials)
        developer_token = self.developer_token_var.get().strip()
        if not developer_token:
            raise ValueError("Developer token is missing.")
        login_id = self.login_customer_var.get().replace("-", "").strip() or None
        refresh_token = getattr(self.credentials, "refresh_token", None)
        if not refresh_token:
            raise ValueError("OAuth refresh token missing; please re-authenticate.")
        client_id, client_secret = self._get_oauth_client_details()
        config = {
            "developer_token": developer_token,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "use_proto_plus": True,
        }
        if login_id:
            config["login_customer_id"] = login_id
        return GoogleAdsClient.load_from_dict(config)

    def _render_results(
        self,
        result: dict,
        lookback: int,
        start_date,
        end_date,
    ) -> None:
        hourly = result.get("hourly", {})
        hourly_table: pd.DataFrame = hourly.get("hourly_table", pd.DataFrame())
        insight = hourly.get("insight", {})
        text = (
            f"Window {start_date} → {end_date} ({lookback} days) • "
            f"First active hour: {insight.get('first_active_hour', 'n/a')} • "
            f"Clicks: {insight.get('first_hour_clicks', 'n/a')} • "
            f"Median other hours: {insight.get('rest_median_clicks', 'n/a')} • "
            f"Spike ratio: {insight.get('spike_ratio', 'n/a')}"
        )
        self.hourly_insight_var.set(text)

        hourly_rows = []
        if not hourly_table.empty:
            for _, row in hourly_table.iterrows():
                hourly_rows.append(
                    {
                        "Hour": int(row.get("segments.hour", 0)),
                        "Clicks": int(row.get("metrics.clicks", 0) or 0),
                        "Impressions": int(row.get("metrics.impressions", 0) or 0),
                        "Conversions": int(row.get("metrics.conversions", 0) or 0),
                        "CTR": self._format_percentage(row.get("ctr")),
                        "CVR": self._format_percentage(row.get("cvr")),
                        "Cost ($)": self._format_currency(row.get("cost")),
                    }
                )
        self._populate_tree(self.hourly_tree, hourly_rows)

        actions = hourly.get("actions", [])
        self._write_actions(actions)

        search_rows = result.get("search_terms", {}).get("negatives", [])
        self._populate_tree(
            self.search_tree,
            [
                {
                    "Search Term": item.get("search_term", ""),
                    "Campaign": item.get("campaign", ""),
                    "Reason": item.get("reason", ""),
                    "Est. Cost ($)": f"{item.get('est_cost', 0.0):.2f}",
                }
                for item in search_rows
            ],
        )

        placement_rows = result.get("placements", {}).get("exclusions", [])
        self._populate_tree(
            self.placement_tree,
            [
                {
                    "Placement": item.get("placement", ""),
                    "Campaign": item.get("campaign", ""),
                    "Reason": item.get("reason", ""),
                    "Est. Cost ($)": f"{item.get('est_cost', 0.0):.2f}",
                }
                for item in placement_rows
            ],
        )

        campaigns = result.get("campaigns", pd.DataFrame())
        campaign_rows = []
        if isinstance(campaigns, pd.DataFrame) and not campaigns.empty:
            top_rows = campaigns.head(25)
            for _, row in top_rows.iterrows():
                campaign_rows.append(
                    {
                        "Campaign ID": row.get("campaign.id", ""),
                        "Name": row.get("campaign.name", ""),
                        "Cost ($)": self._format_currency(row.get("cost")),
                        "Conversions": int(row.get("metrics.conversions", 0) or 0),
                        "CTR": self._format_percentage(row.get("metrics.ctr")),
                        "Clicks": int(row.get("metrics.clicks", 0) or 0),
                        "Impressions": int(row.get("metrics.impressions", 0) or 0),
                    }
                )
        self._populate_tree(self.campaign_tree, campaign_rows)

    # Helpers ----------------------------------------------------------------
    def _populate_tree(self, tree: ttk.Treeview, rows: list[dict]) -> None:
        tree.delete(*tree.get_children())
        columns = tree["columns"]
        for item in rows:
            values = [item.get(col, "") for col in columns]
            tree.insert("", "end", values=values)

    def _write_actions(self, actions: list[str]) -> None:
        self.actions_box.configure(state="normal")
        self.actions_box.delete("1.0", tk.END)
        if actions:
            for action in actions:
                self.actions_box.insert(tk.END, f"• {action}\n")
        else:
            self.actions_box.insert(
                tk.END,
                "No first-hour anomalies detected beyond current thresholds.",
            )
        self.actions_box.configure(state="disabled")

    def _format_percentage(self, value) -> str:
        if value is None or pd.isna(value):
            return "-"
        return f"{float(value) * 100:.1f}%"

    def _format_currency(self, value) -> str:
        if value is None or pd.isna(value):
            return "0.00"
        return f"{float(value):.2f}"

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"[{datetime.now(timezone.utc)}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _gather_settings(self) -> dict:
        return {
            "client_secret_path": self.client_secret_var.get().strip() or "client_secret.json",
            "developer_token": self.developer_token_var.get().strip(),
            "login_customer_id": self.login_customer_var.get().strip(),
            "customer_id": self.customer_id_var.get().strip(),
            "lookback_days": int(self.lookback_var.get()),
            "min_first_hour_clicks": int(self.first_hour_clicks_var.get()),
            "spike_ratio": float(self.spike_ratio_var.get()),
        }

    def _save_settings(self) -> None:
        try:
            data = self._gather_settings()
            save_settings(data)
            self.settings = data
            self._set_status("Settings saved.")
        except Exception as exc:  # noqa: BLE001
            self._log(f"Failed to save settings: {exc}")

    def _get_oauth_client_details(self) -> tuple[str, str]:
        path = Path(self.client_secret_var.get()).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"Client secret file not found at {path}. Please select the correct JSON."
            )
        data = json.loads(path.read_text())
        info = data.get("installed") or data.get("web")
        if not info:
            raise ValueError("Invalid OAuth client JSON; missing 'installed' section.")
        client_id = info.get("client_id")
        client_secret = info.get("client_secret")
        if not client_id or not client_secret:
            raise ValueError("OAuth client JSON must include client_id and client_secret.")
        return client_id, client_secret

    def _show_error_dialog(self, title: str, message: str) -> None:
        if not self.winfo_exists():
            return
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("520x260")
        dialog.minsize(420, 220)

        ttk.Label(dialog, text=title, style="Header.TLabel").pack(anchor="w", padx=12, pady=(12, 6))
        text = tk.Text(dialog, wrap="word", height=8, relief="solid", borderwidth=1)
        text.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        text.insert("1.0", message)
        text.focus_set()

        def block_edit(event):  # pragma: no cover - UI only
            return "break"

        text.bind("<Key>", block_edit)
        text.bind("<<Paste>>", block_edit)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=12, pady=(0, 12))

        def copy_to_clipboard() -> None:
            self.clipboard_clear()
            self.clipboard_append(message)

        ttk.Button(button_frame, text="Copy error", command=copy_to_clipboard).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(button_frame, text="Close", command=dialog.destroy).pack(side="right")

        dialog.lift()


def main() -> None:
    app = GoogleAdsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
