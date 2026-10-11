import QtQuick
import qs.Common
import qs.Widgets
import "StFormat.js" as Fmt

// Stacked category bar with a legend. Up to five categories get their own
// tone from the theme; the rest are folded into "Other".
Column {
    id: root

    property var categories: []          // [{ name, seconds, share, is_app }]
    property int maxSegments: 5

    readonly property var segments: {
        const list = root.categories || [];
        if (list.length <= maxSegments + 1)
            return list;
        const head = list.slice(0, maxSegments);
        let secs = 0, share = 0;
        for (let i = maxSegments; i < list.length; i++) {
            secs += list[i].seconds;
            share += list[i].share;
        }
        head.push({ name: I18n.trFor("screenTime", "Other"), seconds: secs, share: share, is_app: false, other: true });
        return head;
    }

    function toneFor(index, seg) {
        if (seg && seg.other)
            return Theme.withAlpha(Theme.outline, 0.55);
        const tones = [Theme.primary, Theme.tertiary, Theme.secondary,
                       Theme.withAlpha(Theme.primary, 0.5), Theme.withAlpha(Theme.tertiary, 0.5),
                       Theme.withAlpha(Theme.secondary, 0.5)];
        return tones[index % tones.length];
    }

    spacing: Theme.spacingM

    // The bar: segments separated by small gaps, pill-shaped ends.
    Item {
        id: track
        width: parent.width
        height: 12

        readonly property real gap: 3
        readonly property real usable: width - gap * Math.max(0, root.segments.length - 1)

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: Theme.withAlpha(Theme.outline, 0.12)
            visible: root.segments.length === 0
        }

        Repeater {
            model: root.segments.length

            Rectangle {
                required property int index
                readonly property var seg: root.segments[index]
                readonly property real startShare: {
                    let s = 0;
                    for (let i = 0; i < index; i++)
                        s += root.segments[i].share;
                    return s;
                }
                readonly property bool first: index === 0
                readonly property bool last: index === root.segments.length - 1

                x: startShare * track.usable + index * track.gap
                width: Math.max(2, (seg ? seg.share : 0) * track.usable)
                height: track.height
                topLeftRadius: first ? height / 2 : 3
                bottomLeftRadius: first ? height / 2 : 3
                topRightRadius: last ? height / 2 : 3
                bottomRightRadius: last ? height / 2 : 3
                color: root.toneFor(index, seg)

                Behavior on x {
                    NumberAnimation {
                        duration: Theme.mediumDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: Theme.expressiveCurves.standard
                    }
                }
                Behavior on width {
                    NumberAnimation {
                        duration: Theme.mediumDuration
                        easing.type: Easing.BezierSpline
                        easing.bezierCurve: Theme.expressiveCurves.standard
                    }
                }
            }
        }
    }

    // Legend.
    Flow {
        width: parent.width
        spacing: Theme.spacingS

        Repeater {
            model: root.segments.length

            Rectangle {
                required property int index
                readonly property var seg: root.segments[index]

                width: legendRow.implicitWidth + Theme.spacingM * 2
                height: 28
                radius: height / 2
                color: Theme.withAlpha(Theme.surfaceText, 0.05)

                Row {
                    id: legendRow
                    anchors.centerIn: parent
                    spacing: Theme.spacingS

                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 8
                        height: 8
                        radius: 4
                        color: root.toneFor(index, seg)
                    }

                    StyledText {
                        anchors.verticalCenter: parent.verticalCenter
                        text: seg ? seg.name : ""
                        font.pixelSize: Theme.fontSizeSmall
                        font.weight: Font.Medium
                        color: Theme.surfaceText
                    }

                    StyledText {
                        anchors.verticalCenter: parent.verticalCenter
                        text: seg ? Fmt.duration(seg.seconds) : ""
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.surfaceVariantText
                    }
                }
            }
        }
    }
}
