.pragma library

// "2 h 15 min", "45 min", "< 1 min"
function duration(seconds) {
    const total = Math.round((seconds || 0) / 60);
    if (total < 1)
        return seconds > 0 ? "< 1 min" : "0 min";
    const h = Math.floor(total / 60);
    const m = total % 60;
    if (h && m)
        return h + " h " + m + " min";
    if (h)
        return h + " h";
    return m + " min";
}

// "2h 15m", "45m" for the bar pill
function durationShort(seconds) {
    const total = Math.floor((seconds || 0) / 60);
    const h = Math.floor(total / 60);
    const m = total % 60;
    if (h)
        return h + "h " + (m < 10 ? "0" : "") + m + "m";
    return m + "m";
}

// [{value: "2", unit: "h"}, {value: "15", unit: "min"}] for the hero number
function durationParts(seconds) {
    const total = Math.round((seconds || 0) / 60);
    const h = Math.floor(total / 60);
    const m = total % 60;
    const parts = [];
    if (h)
        parts.push({ value: String(h), unit: "h" });
    if (m || !h)
        parts.push({ value: String(m), unit: "min" });
    return parts;
}

// Gridline step in seconds: 2-4 lines for the given maximum.
function niceStep(maxSeconds, unit) {
    const steps = unit === "hour"
        ? [300, 600, 900, 1200, 1800]
        : [900, 1800, 3600, 7200, 10800, 14400, 21600, 28800];
    for (let i = 0; i < steps.length; i++) {
        if (maxSeconds / steps[i] <= 3)
            return steps[i];
    }
    return steps[steps.length - 1];
}

function axisLabel(seconds) {
    if (seconds >= 3600 && seconds % 3600 === 0)
        return (seconds / 3600) + " h";
    if (seconds >= 3600)
        return (seconds / 3600).toFixed(1) + " h";
    return Math.round(seconds / 60) + " min";
}

function parseDate(iso) {
    const p = (iso || "").split("-");
    return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
}

function isoDate(d) {
    const pad = n => (n < 10 ? "0" : "") + n;
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
}

function addDays(iso, n) {
    const d = parseDate(iso);
    d.setDate(d.getDate() + n);
    return isoDate(d);
}

function mondayOf(iso) {
    const d = parseDate(iso);
    const back = (d.getDay() + 6) % 7;
    d.setDate(d.getDate() - back);
    return isoDate(d);
}

// DMS's tooltip auto-detects rich text. Window titles come from websites, so
// replace the characters that could turn one into HTML (e.g. a remote <img>).
function plain(text) {
    return String(text || "").replace(/</g, "‹").replace(/>/g, "›").replace(/&/g, "＆");
}

// Locale for weekday and month names. The plugin's text is English-only, so
// dates are English too instead of mixing in the system locale. Once
// translations exist, return the DMS UI locale for translated languages.
function locale() {
    return Qt.locale("en_US");
}
