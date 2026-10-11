import QtQuick
import qs.Common
import qs.Widgets
import "StFormat.js" as Fmt

// Vertical bar chart. Buckets: [{ seconds, is_current, is_future, label, tip }].
// The current bucket uses the accent colour, the rest a muted tone; hovering
// shows a tooltip with the exact duration.
Item {
    id: root

    property var buckets: []
    property string unit: "hour"          // "hour" | "day": picks gridline steps
    property real averageSeconds: -1      // dashed reference line when >= 0
    property bool showAxis: true
    property bool interactive: false
    property int labelHeight: 20

    signal activated(int index)
    signal replay

    readonly property real axisWidth: showAxis ? 44 : 0
    readonly property real plotWidth: width - axisWidth
    readonly property real plotHeight: height - labelHeight
    readonly property real maxValue: {
        let m = 0;
        for (let i = 0; i < buckets.length; i++)
            m = Math.max(m, buckets[i].seconds || 0);
        return Math.max(m, averageSeconds);
    }
    readonly property real step: Fmt.niceStep(Math.max(maxValue, 1), unit)
    readonly property real scaleTop: Math.max(step, Math.ceil(maxValue / step) * step)
    readonly property real slotWidth: buckets.length ? plotWidth / buckets.length : 0
    readonly property real barWidth: Math.max(3, Math.min(28, slotWidth * (buckets.length > 12 ? 0.62 : 0.5)))
    readonly property int staggerMs: buckets.length ? Math.round(Theme.expressiveDurations.normal * 0.6 / buckets.length) : 0
    property int hoverIndex: -1

    function yFor(seconds) {
        return plotHeight - seconds / scaleTop * plotHeight;
    }

    // Gridlines and their labels.
    Repeater {
        model: Math.round(root.scaleTop / root.step) + 1

        Item {
            required property int index
            readonly property real value: index * root.step
            y: root.yFor(value)
            width: root.width
            height: 1

            Rectangle {
                width: root.plotWidth
                height: 1
                color: index === 0 ? Theme.outlineMedium : Theme.withAlpha(Theme.outline, 0.12)
            }

            StyledText {
                visible: root.showAxis && index > 0
                x: root.plotWidth + Theme.spacingS
                anchors.verticalCenter: parent.verticalCenter
                text: Fmt.axisLabel(parent.value)
                font.pixelSize: Theme.fontSizeSmall - 2
                color: Theme.surfaceVariantText
            }
        }
    }

    // Average reference line.
    Item {
        id: avgLine
        visible: root.averageSeconds > 0
        y: root.yFor(Math.max(0, root.averageSeconds))
        width: root.plotWidth
        height: 1

        Behavior on y {
            NumberAnimation {
                duration: Theme.mediumDuration
                easing.type: Easing.BezierSpline
                easing.bezierCurve: Theme.expressiveCurves.standard
            }
        }

        Row {
            spacing: 4
            Repeater {
                model: Math.ceil(avgLine.width / 8)
                Rectangle {
                    width: 4
                    height: 1.5
                    radius: 1
                    color: Theme.withAlpha(Theme.tertiary, 0.9)
                }
            }
        }

        StyledText {
            visible: root.showAxis
            x: root.plotWidth + Theme.spacingS
            anchors.verticalCenter: parent.verticalCenter
            text: I18n.trFor("screenTime", "avg")
            font.pixelSize: Theme.fontSizeSmall - 2
            font.weight: Font.DemiBold
            color: Theme.tertiary
        }
    }

    // Bars.
    Repeater {
        id: bars
        model: root.buckets.length

        Item {
            id: slot

            required property int index
            readonly property var bucket: root.buckets[index] || ({})
            readonly property real target: (bucket.seconds || 0) / root.scaleTop * root.plotHeight
            readonly property bool hovered: root.hoverIndex === index
            property real reveal: 0

            x: index * root.slotWidth
            width: root.slotWidth
            height: root.plotHeight

            Rectangle {
                id: bar
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter
                width: root.barWidth
                height: slot.bucket.seconds > 0 ? Math.max(3, slot.target * slot.reveal) : 0
                topLeftRadius: Math.min(width / 2, 8)
                topRightRadius: Math.min(width / 2, 8)
                bottomLeftRadius: 2
                bottomRightRadius: 2
                color: {
                    if (slot.bucket.is_current)
                        return Theme.primary;
                    return Theme.withAlpha(Theme.primary, slot.hovered ? 0.62 : 0.34);
                }

                Behavior on height {
                    enabled: slot.reveal >= 1
                    NumberAnimation {
                        duration: Theme.mediumDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: Theme.expressiveCurves.standard
                    }
                }

                Behavior on color {
                    ColorAnimation {
                        duration: Theme.shorterDuration
                    }
                }
            }

            // Placeholder nub so empty buckets still read as part of the axis.
            Rectangle {
                visible: !(slot.bucket.seconds > 0)
                anchors.bottom: parent.bottom
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(root.barWidth, 6)
                height: 3
                radius: 1.5
                color: Theme.withAlpha(Theme.outline, slot.bucket.is_future ? 0.12 : 0.28)
            }

            SequentialAnimation {
                id: revealAnim
                PauseAnimation {
                    duration: slot.index * root.staggerMs
                }
                NumberAnimation {
                    target: slot
                    property: "reveal"
                    from: 0
                    to: 1
                    duration: Theme.expressiveDurations.large
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: Theme.expressiveCurves.emphasizedDecel
                }
            }

            Connections {
                target: root
                function onReplay() {
                    slot.reveal = 0;
                    revealAnim.restart();
                }
            }

            Component.onCompleted: revealAnim.start()

            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: root.interactive && !slot.bucket.is_future ? Qt.PointingHandCursor : Qt.ArrowCursor
                onEntered: root.hoverIndex = slot.index
                onExited: {
                    if (root.hoverIndex === slot.index)
                        root.hoverIndex = -1;
                }
                onClicked: {
                    if (root.interactive && !slot.bucket.is_future)
                        root.activated(slot.index);
                }
            }
        }
    }

    // X-axis labels.
    Repeater {
        model: root.buckets.length

        StyledText {
            required property int index
            readonly property var bucket: root.buckets[index] || ({})
            visible: (bucket.label || "") !== ""
            x: index * root.slotWidth + (root.slotWidth - width) / 2
            y: root.plotHeight + 4
            text: bucket.label || ""
            font.pixelSize: Theme.fontSizeSmall - 1
            font.weight: bucket.is_current ? Font.DemiBold : Font.Normal
            color: bucket.is_current ? Theme.primary : Theme.surfaceVariantText
        }
    }

    // Tooltip.
    Rectangle {
        id: tip

        readonly property var bucket: root.hoverIndex >= 0 ? root.buckets[root.hoverIndex] : null
        readonly property real barTop: bucket ? root.yFor(bucket.seconds || 0) : 0

        visible: opacity > 0
        opacity: bucket && !bucket.is_future ? 1 : 0
        width: tipText.implicitWidth + Theme.spacingM * 2
        height: tipText.implicitHeight + Theme.spacingS * 1.5
        radius: Theme.cornerRadius / 2
        color: Theme.surfaceText
        z: 10
        x: {
            const center = (root.hoverIndex + 0.5) * root.slotWidth;
            return Math.max(0, Math.min(root.width - width, center - width / 2));
        }
        y: Math.max(-height / 2, barTop - height - 6)

        Behavior on opacity {
            NumberAnimation {
                duration: Theme.shorterDuration
            }
        }
        Behavior on x {
            enabled: tip.opacity > 0
            NumberAnimation {
                duration: Theme.shorterDuration
                easing.type: Easing.OutCubic
            }
        }

        StyledText {
            id: tipText
            anchors.centerIn: parent
            text: tip.bucket ? (tip.bucket.tip || "") : ""
            font.pixelSize: Theme.fontSizeSmall
            font.weight: Font.Medium
            color: Theme.surface
        }
    }
}
