import QtQuick
import qs.Common
import qs.Widgets
import "StFormat.js" as Fmt

// One app's numbers: header, stat tiles and its daily usage chart
// (past 7 days in Day view, the selected week in Week view).
Column {
    id: root

    property var app: null
    property var summary: null
    property string kind: "day"
    property string rangeLabel: ""
    property var titles: null           // summary --app output, null while loading

    signal back

    function tr(s) {
        return I18n.trFor("screenTime", s);
    }

    readonly property var history: app ? app.history : []
    readonly property var dates: summary ? summary.history_dates : []
    readonly property real historyTotal: history.reduce((a, b) => a + b, 0)
    readonly property int elapsedDays: {
        if (!summary)
            return 1;
        let n = 0;
        for (let i = 0; i < dates.length; i++) {
            if (dates[i] <= summary.range.today)
                n++;
        }
        return Math.max(1, n);
    }

    spacing: Theme.spacingM

    // Header: back, icon, name, category.
    Item {
        width: parent.width
        height: 56

        DankActionButton {
            id: backButton
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            iconName: "arrow_back"
            buttonSize: 36
            onClicked: root.back()
        }

        StAppIcon {
            id: bigIcon
            anchors.left: backButton.right
            anchors.leftMargin: Theme.spacingS
            anchors.verticalCenter: parent.verticalCenter
            iconSize: 44
            appId: root.app ? root.app.app_id : ""
            icon: root.app ? (root.app.icon || "") : ""
            name: root.app ? root.app.name : ""
        }

        Column {
            anchors.left: bigIcon.right
            anchors.leftMargin: Theme.spacingM
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            StyledText {
                width: parent.width
                elide: Text.ElideRight
                text: root.app ? root.app.name : ""
                font.pixelSize: Theme.fontSizeLarge + 2
                font.weight: Font.DemiBold
                color: Theme.surfaceText
            }
            StyledText {
                width: parent.width
                elide: Text.ElideRight
                text: root.app ? (root.app.category || root.app.app_id) : ""
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceVariantText
            }
        }
    }

    // Stat tiles.
    Row {
        id: tiles
        width: parent.width
        spacing: Theme.spacingS

        readonly property real tileWidth: (width - spacing * 2) / 3

        Repeater {
            model: [
                { label: root.rangeLabel, value: Fmt.duration(root.app ? root.app.seconds : 0) },
                {
                    label: root.kind === "day" ? root.tr("7-day average") : root.tr("Per day"),
                    value: Fmt.duration(root.kind === "day" ? root.historyTotal / 7 : (root.app ? root.app.seconds : 0) / root.elapsedDays)
                },
                { label: root.tr("Share"), value: Math.round((root.app ? root.app.share : 0) * 100) + " %" }
            ]

            Rectangle {
                required property var modelData
                width: tiles.tileWidth
                height: 68
                radius: Theme.cornerRadius
                color: Theme.nestedSurface
                border.color: Theme.outlineMedium
                border.width: 1

                Column {
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.spacingM
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.spacingS
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4

                    StyledText {
                        width: parent.width
                        elide: Text.ElideRight
                        text: modelData.label
                        font.pixelSize: Theme.fontSizeSmall - 1
                        color: Theme.surfaceVariantText
                    }
                    NumericText {
                        width: parent.width
                        elide: Text.ElideRight
                        isMonospace: false
                        text: modelData.value
                        font.pixelSize: Theme.fontSizeLarge
                        font.weight: Font.DemiBold
                        color: Theme.surfaceText
                    }
                }
            }
        }
    }

    StCard {
        width: parent.width
        title: root.kind === "day" ? root.tr("Past 7 days") : root.tr("Daily usage")
        pad: Theme.spacingL

        StBarChart {
            id: chart
            width: parent.width
            height: 150
            unit: "day"
            averageSeconds: root.historyTotal > 0 ? root.historyTotal / (root.kind === "day" ? 7 : root.elapsedDays) : -1
            buckets: {
                if (!root.summary || !root.app)
                    return [];
                const loc = Qt.locale();
                const today = root.summary.range.today;
                const out = [];
                for (let i = 0; i < root.dates.length; i++) {
                    const d = Fmt.parseDate(root.dates[i]);
                    out.push({
                        seconds: root.history[i] || 0,
                        is_current: root.dates[i] === (root.kind === "day" ? root.summary.range.anchor : today),
                        is_future: root.dates[i] > today,
                        label: loc.dayName(d.getDay(), Locale.ShortFormat),
                        tip: d.toLocaleDateString(loc, "ddd, d MMM") + " · " + Fmt.duration(root.history[i] || 0)
                    });
                }
                return out;
            }
        }
    }

    // Window titles.
    StCard {
        id: windowsCard
        width: parent.width
        title: root.tr("Windows")
        trailing: root.titles && root.titles.tracking && root.titles.retention_days > 0
            ? root.tr("kept %1 days").arg(root.titles.retention_days) : ""

        readonly property var items: root.titles ? root.titles.items : []
        readonly property real topSeconds: items.length ? Math.max(1, items[0].seconds) : 1

        DankTooltipV2 {
            id: titleTip
        }

        Column {
            width: parent.width
            spacing: Theme.spacingXS

            // Loading.
            StyledText {
                visible: root.titles === null
                width: parent.width
                text: root.tr("Loading…")
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceVariantText
            }

            // Hints when there is nothing to break down.
            Row {
                visible: root.titles !== null && windowsCard.items.length === 0
                width: parent.width
                spacing: Theme.spacingS

                DankIcon {
                    name: root.titles && !root.titles.tracking ? "visibility_off" : "info"
                    size: Theme.iconSizeSmall
                    color: Theme.surfaceVariantText
                }
                StyledText {
                    width: parent.width - Theme.iconSizeSmall - Theme.spacingS
                    wrapMode: Text.WordWrap
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.surfaceVariantText
                    text: {
                        if (!root.titles)
                            return "";
                        if (!root.titles.tracking)
                            return root.tr("Turn on “Record window titles” in the Screen Time plugin settings to see which windows you used.");
                        if (root.titles.unrecorded_seconds > 0)
                            return root.tr("No window titles recorded in this period yet. Time from before title recording was turned on isn't broken down.");
                        return root.tr("No window titles recorded in this period yet.");
                    }
                }
            }

            Repeater {
                model: windowsCard.items

                Item {
                    id: titleRow
                    required property var modelData
                    width: parent.width
                    height: 44

                    Rectangle {
                        anchors.fill: parent
                        anchors.leftMargin: -Theme.spacingS
                        anchors.rightMargin: -Theme.spacingS
                        radius: Theme.cornerRadius
                        color: titleMouse.containsMouse ? Theme.surfaceTextHover : Theme.withAlpha(Theme.surfaceTextHover, 0)

                        Behavior on color {
                            ColorAnimation {
                                duration: Theme.shorterDuration
                            }
                        }
                    }

                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        Item {
                            width: parent.width
                            height: titleText.implicitHeight

                            StyledText {
                                id: titleText
                                anchors.left: parent.left
                                anchors.right: titleDuration.left
                                anchors.rightMargin: Theme.spacingM
                                text: titleRow.modelData.title
                                elide: Text.ElideRight
                                font.pixelSize: Theme.fontSizeSmall + 1
                                color: Theme.surfaceText
                            }
                            NumericText {
                                id: titleDuration
                                anchors.right: parent.right
                                anchors.verticalCenter: titleText.verticalCenter
                                isMonospace: false
                                text: Fmt.duration(titleRow.modelData.seconds)
                                font.pixelSize: Theme.fontSizeSmall
                                color: Theme.surfaceVariantText
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 4
                            radius: 2
                            color: Theme.withAlpha(Theme.tertiary, 0.14)

                            Rectangle {
                                height: parent.height
                                radius: parent.radius
                                width: Math.max(height, parent.width * titleRow.modelData.seconds / windowsCard.topSeconds)
                                color: Theme.tertiary

                                Behavior on width {
                                    NumberAnimation {
                                        duration: Theme.mediumDuration
                                        easing.type: Easing.BezierSpline
                                        easing.bezierCurve: Theme.expressiveCurves.emphasizedDecel
                                    }
                                }
                            }
                        }
                    }

                    MouseArea {
                        id: titleMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onEntered: {
                            if (titleText.truncated)
                                titleTip.show(Fmt.plain(titleRow.modelData.title), titleText, 0, 0, "top");
                        }
                        onExited: titleTip.hide()
                    }
                }
            }

            // Remainders.
            Repeater {
                model: root.titles ? [
                    { label: root.tr("Other windows"), seconds: root.titles.other_seconds },
                    { label: root.tr("Not recorded"), seconds: root.titles.unrecorded_seconds }
                ].filter(r => r.seconds >= 60 && windowsCard.items.length > 0) : []

                Item {
                    required property var modelData
                    width: parent.width
                    height: 28

                    StyledText {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        font.pixelSize: Theme.fontSizeSmall
                        font.italic: true
                        color: Theme.surfaceVariantText
                    }
                    NumericText {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        isMonospace: false
                        text: Fmt.duration(modelData.seconds)
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.surfaceVariantText
                    }
                }
            }
        }
    }

    // Replay the grow-in only when a different app is opened, not on refresh.
    readonly property string appKey: app ? app.app_id : ""
    onAppKeyChanged: {
        if (appKey)
            chart.replay();
    }
}
