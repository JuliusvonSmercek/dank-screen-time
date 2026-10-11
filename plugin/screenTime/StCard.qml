import QtQuick
import qs.Common
import qs.Widgets

// Tonal card matching DankDash's overview cards, with an optional title row.
Rectangle {
    id: card

    property string title: ""
    property string trailing: ""
    property int pad: Theme.spacingM
    default property alias content: body.data

    implicitHeight: column.implicitHeight + pad * 2
    radius: Theme.cornerRadius
    color: Theme.nestedSurface
    border.color: Theme.outlineMedium
    border.width: 1

    Column {
        id: column
        x: card.pad
        y: card.pad
        width: card.width - card.pad * 2
        spacing: Theme.spacingM

        Item {
            width: parent.width
            height: titleText.implicitHeight
            visible: card.title !== ""

            StyledText {
                id: titleText
                text: card.title
                font.pixelSize: Theme.fontSizeMedium
                font.weight: Font.DemiBold
                color: Theme.surfaceText
            }

            StyledText {
                anchors.right: parent.right
                anchors.verticalCenter: titleText.verticalCenter
                text: card.trailing
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.surfaceVariantText
            }
        }

        Item {
            id: body
            width: parent.width
            implicitHeight: childrenRect.height
            height: implicitHeight
        }
    }
}
