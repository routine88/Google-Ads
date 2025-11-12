function main() {
  var lookbackDays = 14;
  var minClicks = 50;        // Require at least this many clicks at the first hour.
  var spikeRatio = 2.5;      // First-hour clicks vs. median of other hours.
  var email = "you@example.com"; // Replace with your alert email.

  var report = AdsApp.report(
    'SELECT Date, HourOfDay, Clicks, Impressions, Conversions ' +
    'FROM ACCOUNT_PERFORMANCE_REPORT ' +
    'DURING LAST_' + lookbackDays + '_DAYS'
  );

  var byHour = {};
  var rows = report.rows();
  while (rows.hasNext()) {
    var r = rows.next();
    var hour = parseInt(r['HourOfDay'], 10);
    byHour[hour] = byHour[hour] || {clicks: 0, imps: 0, conv: 0};
    byHour[hour].clicks += parseInt(r['Clicks'], 10);
    byHour[hour].imps += parseInt(r['Impressions'], 10);
    byHour[hour].conv += parseInt(r['Conversions'] || '0', 10);
  }

  var activeHours = [];
  for (var h = 0; h < 24; h++) {
    if (byHour[h] && byHour[h].clicks > 0) {
      activeHours.push(h);
    }
  }

  if (activeHours.length === 0) {
    Logger.log('No hourly data.');
    return;
  }

  var firstHour = activeHours[0];
  var firstClicks = byHour[firstHour].clicks;
  var others = [];
  for (var i = 0; i < activeHours.length; i++) {
    var hourVal = activeHours[i];
    if (hourVal !== firstHour) {
      others.push(byHour[hourVal].clicks);
    }
  }
  var median = 0;
  if (others.length > 0) {
    others.sort(function(a, b){ return a - b; });
    median = others[Math.floor(others.length / 2)];
  }
  var ratio = median > 0 ? (firstClicks / median) : null;

  if (ratio && ratio >= spikeRatio && firstClicks >= minClicks) {
    var subject = 'Google Ads: Hour-0 click spike detected';
    var body = ''
      + 'First active hour (account time): ' + firstHour + ':00<br>'
      + 'Clicks at first hour: ' + firstClicks + '<br>'
      + 'Median clicks other hours: ' + median + '<br>'
      + 'Spike ratio: ' + ratio.toFixed(2);
    MailApp.sendEmail({
      to: email,
      subject: subject,
      htmlBody: body
    });
  } else {
    Logger.log('No spike detected. First-hour clicks=' + firstClicks + ', ratio=' + ratio);
  }
}
