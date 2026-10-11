import QtQuick
import qs.Common
import qs.Widgets

// App icon from the CLI's `icon` (absolute path or icon name), resolved the
// same way DMS resolves window icons, with a tonal letter avatar fallback.
AppIconRenderer {
    id: root

    property string appId: ""
    property string icon: ""
    property string name: ""

    iconSize: 32
    width: iconSize
    height: iconSize
    iconValue: {
        if (icon.startsWith("/"))
            return "image:" + icon;
        return icon || appId || "application-x-executable";
    }
    fallbackText: (name || appId || "?").charAt(0).toUpperCase()
    fallbackBackgroundColor: Theme.primaryContainer
    fallbackTextColor: Theme.primary
}
