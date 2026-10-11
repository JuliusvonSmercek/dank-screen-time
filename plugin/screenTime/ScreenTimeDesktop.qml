import QtQuick
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins
import "StFormat.js" as Fmt

// Desktop card: today's total, hourly chart and top apps.
DesktopPluginComponent {
    id: root

    minWidth: 240
    minHeight: 200


    readonly property var today: PluginService.globalVars["screenTime"]?.cache?.["day:"]?.data ?? null
    readonly property real backgroundOpacity: (pluginData.desktopOpacity ?? 85) / 100
    readonly property int topCount: height > 380 ? 5 : (height > 300 ? 3 : (height > 250 ? 2 : 0))

    function tr(s) {
        return I18n.trFor("screenTime", s);
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.cornerRadius
        color: Theme.withAlpha(Theme.surfaceContainer, root.backgroundOpacity)
        border.color: Theme.outlineMedium
        border.width: 1
    }

    Column {
        id: content
        anchors.fill: parent
        anchors.margins: Theme.spacingL
        spacing: Theme.spacingM

        Item {
            width: parent.width
            height: header.implicitHeight

            Column {
                id: header
                spacing: 2

                StyledText {
                    text: root.tr("Screen Time · Today")
                    font.pixelSize: Theme.fontSizeSmall
                    font.weight: Font.Medium
                    color: Theme.surfaceVariantText
                }
                NumericText {
                    isMonospace: false
                    text: root.today ? Fmt.duration(root.today.total_seconds) : "--"
                    font.pixelSize: Theme.fontSizeXLarge + 8
                    font.weight: Font.Medium
                    color: Theme.surfaceText
                }
            }

            DankIcon {
                anchors.right: parent.right
                anchors.top: parent.top
                name: root.today && root.today.daemon.running ? "timelapse" : "timer_off"
                size: Theme.iconSize
                color: root.today && root.today.daemon.running ? Theme.primary : Theme.error
            }
        }

        StBarChart {
            id: chart
            width: parent.width
            height: Math.max(60, parent.height - header.height - Theme.spacingM - (appsColumn.visible ? appsColumn.height + Theme.spacingM : 0))
            showAxis: false
            labelHeight: 16
            unit: "hour"
            buckets: {
                if (!root.today)
                    return [];
                const pad = n => (n < 10 ? "0" : "") + n;
                return root.today.chart.buckets.map(b => ({
                    seconds: b.seconds,
                    is_current: b.is_current,
                    is_future: b.is_future,
                    label: b.hour % 6 === 0 ? String(b.hour) : "",
                    tip: pad(b.hour) + ":00 · " + Fmt.duration(b.seconds)
                }));
            }
        }

        Column {
            id: appsColumn
            width: parent.width
            spacing: 2
            visible: root.topCount > 0

            Repeater {
                model: root.today ? root.today.apps.slice(0, root.topCount) : []

                StAppRow {
                    required property var modelData
                    width: appsColumn.width
                    compact: true
                    appId: modelData.app_id
                    name: modelData.name
                    icon: modelData.icon || ""
                    seconds: modelData.seconds
                    fraction: root.today.apps.length ? modelData.seconds / Math.max(1, root.today.apps[0].seconds) : 0
                    enabled: false   // static on the desktop: no hover, no click
                }
            }
        }
    }
}
