import QtQuick
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins
import "StFormat.js" as Fmt

// Desktop card. Each instance shows either today (hourly chart) or this week
// (daily chart with the average line); pick it in the instance's settings.
// Left click opens the bar pill's popout on the same screen (right-drag moves
// the widget, as for every DMS desktop widget).
DesktopPluginComponent {
    id: root

    minWidth: 240
    minHeight: 200

    property var screen: null       // injected by DesktopPluginWrapper

    readonly property string view: pluginData.view === "week" ? "week" : "day"
    readonly property bool openOnClick: pluginData.openOnClick ?? true
    readonly property var summary: PluginService.globalVars["screenTime"]?.cache?.[view + ":"]?.data ?? null
    readonly property real backgroundOpacity: (pluginData.desktopOpacity ?? 85) / 100
    readonly property int topCount: height > 400 ? 5 : (height > 320 ? 3 : (height > 260 ? 2 : 0))

    function tr(s) {
        return I18n.trFor("screenTime", s);
    }

    function openPopout() {
        PluginService.setGlobalVar("screenTime", "openRequest", {
            t: Date.now(),
            kind: root.view,
            screen: root.screen ? root.screen.name : "",
            toggle: false
        });
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.cornerRadius
        color: Theme.withAlpha(Theme.surfaceContainer, root.backgroundOpacity)
        border.color: Theme.outlineMedium
        border.width: 1
    }

    Column {
        anchors.fill: parent
        anchors.margins: Theme.spacingL
        spacing: Theme.spacingM

        Item {
            id: header
            width: parent.width
            height: headerColumn.implicitHeight

            Column {
                id: headerColumn
                width: parent.width - statusIcon.width - Theme.spacingS
                spacing: 2

                StyledText {
                    text: root.view === "week" ? root.tr("Screen Time · This week") : root.tr("Screen Time · Today")
                    font.pixelSize: Theme.fontSizeSmall
                    font.weight: Font.Medium
                    color: Theme.surfaceVariantText
                }
                NumericText {
                    isMonospace: false
                    text: root.summary ? Fmt.duration(root.summary.total_seconds) : "--"
                    font.pixelSize: Theme.fontSizeXLarge + 8
                    font.weight: Font.Medium
                    color: Theme.surfaceText
                }
                StyledText {
                    width: parent.width
                    elide: Text.ElideRight
                    visible: !!root.summary
                    text: {
                        if (!root.summary)
                            return "";
                        if (root.view === "week")
                            return root.tr("%1 per day").arg(Fmt.duration(root.summary.compare_seconds));
                        const avg = root.summary.average_seconds;
                        return avg > 0 ? root.tr("7-day average %1").arg(Fmt.duration(avg)) : root.tr("No 7-day average yet");
                    }
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.surfaceVariantText
                }
            }

            DankIcon {
                id: statusIcon
                anchors.right: parent.right
                anchors.top: parent.top
                name: root.summary && root.summary.daemon.running ? "timelapse" : "timer_off"
                size: Theme.iconSize
                color: root.summary && root.summary.daemon.running ? Theme.primary : Theme.error
            }
        }

        StBarChart {
            id: chart
            width: parent.width
            height: Math.max(60, parent.height - header.height - Theme.spacingM - (appsColumn.visible ? appsColumn.height + Theme.spacingM : 0))
            showAxis: false
            labelHeight: 16
            unit: root.view === "week" ? "day" : "hour"
            averageSeconds: root.view === "week" && root.summary && root.summary.compare_seconds > 0 ? root.summary.compare_seconds : -1
            buckets: {
                if (!root.summary)
                    return [];
                const loc = Fmt.locale();
                const pad = n => (n < 10 ? "0" : "") + n;
                return root.summary.chart.buckets.map(b => {
                    if (root.view === "week") {
                        const d = Fmt.parseDate(b.date);
                        return {
                            seconds: b.seconds,
                            is_current: b.is_current,
                            is_future: b.is_future,
                            label: loc.dayName(b.weekday % 7, Locale.ShortFormat),
                            tip: d.toLocaleDateString(loc, "ddd, d MMM") + " · " + Fmt.duration(b.seconds)
                        };
                    }
                    return {
                        seconds: b.seconds,
                        is_current: b.is_current,
                        is_future: b.is_future,
                        label: b.hour % 6 === 0 ? String(b.hour) : "",
                        tip: pad(b.hour) + ":00 · " + Fmt.duration(b.seconds)
                    };
                });
            }
        }

        Column {
            id: appsColumn
            width: parent.width
            spacing: 2
            visible: root.topCount > 0

            Repeater {
                model: root.summary ? root.summary.apps.slice(0, root.topCount) : []

                StAppRow {
                    required property var modelData
                    width: appsColumn.width
                    compact: true
                    appId: modelData.app_id
                    name: modelData.name
                    icon: modelData.icon || ""
                    seconds: modelData.seconds
                    fraction: modelData.seconds / Math.max(1, root.summary.apps[0].seconds)
                    enabled: false   // static rows; the whole card is the click target
                }
            }
        }
    }

    // Click target on top. It doesn't accept hover, so the chart tooltips
    // underneath keep working.
    MouseArea {
        anchors.fill: parent
        z: 10
        enabled: root.openOnClick
        acceptedButtons: Qt.LeftButton
        cursorShape: Qt.PointingHandCursor
        onClicked: root.openPopout()
    }

    onViewChanged: chart.replay()
}
