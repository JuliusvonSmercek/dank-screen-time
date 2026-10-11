import QtQuick
import qs.Common
import qs.Services
import qs.Widgets
import qs.Modules.Plugins
import "StFormat.js" as Fmt

// Bar pill: today's total, optionally with the top app's icon. Clicking it
// opens the Screen Time popout.
PluginComponent {
    id: root

    layerNamespacePlugin: "screen-time"

    readonly property var today: PluginService.globalVars["screenTime"]?.cache?.["day:"]?.data ?? null
    readonly property var cli: PluginService.globalVars["screenTime"]?.cli ?? null
    readonly property bool showTopApp: pluginData.showTopAppIcon ?? true
    readonly property var topApp: today && today.apps.length ? today.apps[0] : null
    readonly property string totalText: today ? Fmt.durationShort(today.total_seconds) : "--"
    readonly property bool tracking: today ? today.daemon.running : false
    readonly property real textSize: Theme.barTextSize(barThickness, barConfig?.fontScale, barConfig?.maximizeWidgetText)

    horizontalBarPill: Component {
        Row {
            spacing: Theme.spacingXS + 2

            Item {
                anchors.verticalCenter: parent.verticalCenter
                width: root.iconSize
                height: root.iconSize

                StAppIcon {
                    anchors.fill: parent
                    visible: root.showTopApp && root.topApp !== null
                    iconSize: root.iconSize
                    appId: root.topApp ? root.topApp.app_id : ""
                    icon: root.topApp ? (root.topApp.icon || "") : ""
                    name: root.topApp ? root.topApp.name : ""
                }

                DankIcon {
                    anchors.centerIn: parent
                    visible: !root.showTopApp || root.topApp === null
                    name: root.tracking || !root.today ? "timelapse" : "timer_off"
                    size: root.iconSize
                    color: Theme.widgetIconColor
                }
            }

            NumericText {
                anchors.verticalCenter: parent.verticalCenter
                isMonospace: false
                text: root.totalText
                font.pixelSize: root.textSize
                color: root.tracking || !root.today ? Theme.widgetTextColor : Theme.withAlpha(Theme.widgetTextColor, 0.6)
            }
        }
    }

    verticalBarPill: Component {
        Column {
            spacing: 2

            DankIcon {
                anchors.horizontalCenter: parent.horizontalCenter
                name: "timelapse"
                size: root.iconSize
                color: Theme.widgetIconColor
            }

            Repeater {
                model: root.today ? Fmt.durationShort(root.today.total_seconds).split(" ") : ["--"]

                NumericText {
                    required property string modelData
                    anchors.horizontalCenter: parent.horizontalCenter
                    isMonospace: false
                    text: modelData
                    font.pixelSize: Theme.barTextSize(root.barThickness, root.barConfig?.fontScale, root.barConfig?.maximizeWidgetText) - 1
                    color: Theme.widgetTextColor
                }
            }
        }
    }

    popoutWidth: 460
    popoutHeight: 680

    popoutContent: Component {
        ScreenTimePopout {}
    }
}
