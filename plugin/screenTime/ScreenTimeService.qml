import QtQuick
import Quickshell.Io
import qs.Common
import qs.Services
import qs.Modules.Plugins

// Background surface (instantiated once): the only place that runs the
// `screentime` CLI. Results are published as plugin global vars so every bar
// pill, popout and desktop widget shares one fetch.
//
//   globalVars.screenTime.cache   { "<kind>:<date>[|<app_id>]": { data, fetchedAt } }
//                                 date "" = current; "|app" adds that app's window titles
//   globalVars.screenTime.cli     { ok, missing, error }
//   globalVars.screenTime.request { key, force, t }   written by the UI
PluginComponent {
    id: root

    readonly property string pid: "screenTime"
    property int refreshMs: Math.max(15, parseInt(pluginData.refreshInterval || "60")) * 1000
    property var inFlight: ({})
    property var pushed: ({})

    readonly property var request: PluginService.globalVars[pid]?.request ?? null

    function cache() {
        return PluginService.getGlobalVar(pid, "cache", {});
    }

    function cliCommand(args) {
        // ~/.local/bin is where install.sh puts the CLI; it may be missing from DMS's PATH.
        return ["sh", "-c", "PATH=\"$PATH:$HOME/.local/bin\"; exec screentime \"$@\"", "screentime"].concat(args);
    }

    function fetch(key) {
        if (inFlight[key])
            return;
        const [rangeKey, app] = key.split("|");
        const parts = rangeKey.split(":");
        const args = ["summary", "--range", parts[0], "--json"];
        if (parts[1])
            args.push("--date", parts[1]);
        if (app)
            args.push("--app", app);
        inFlight[key] = true;
        Proc.runCommand("screenTime." + key, cliCommand(args), (stdout, exitCode) => {
            delete inFlight[key];
            if (exitCode === 127) {
                PluginService.setGlobalVar(pid, "cli", { ok: false, missing: true, error: "" });
                return;
            }
            let data = null;
            try {
                data = exitCode === 0 ? JSON.parse(stdout) : null;
            } catch (e) {
                data = null;
            }
            if (!data) {
                PluginService.setGlobalVar(pid, "cli", { ok: false, missing: false, error: "screentime exited with code " + exitCode });
                return;
            }
            PluginService.setGlobalVar(pid, "cli", { ok: true, missing: false, error: "" });
            const next = Object.assign({}, cache());
            next[key] = { data: data, fetchedAt: Date.now() };
            PluginService.setGlobalVar(pid, "cache", next);
        }, 0);
    }

    function refreshCurrent() {
        fetch("day:");
        fetch("week:");
    }

    function maxAge(key) {
        // Past ranges only change if the day boundary setting changes.
        return key.split("|")[0].endsWith(":") ? 5000 : 600000;
    }

    onRequestChanged: {
        if (!request || !request.key)
            return;
        const entry = cache()[request.key];
        const age = entry ? Date.now() - entry.fetchedAt : Infinity;
        if (!entry || age > (request.force ? 3000 : maxAge(request.key)))
            fetch(request.key);
    }

    // -- settings -> ~/.config/screentime/config.toml ------------------------

    function pushSetting(key, configKey, value) {
        if (value === undefined || value === null || pushed[key] === String(value))
            return;
        pushed[key] = String(value);
        Proc.runCommand("screenTime.config." + configKey, cliCommand(["config", "set", configKey, String(value)]), (stdout, exitCode) => {
            if (exitCode !== 0) {
                delete pushed[key];
                return;
            }
            if (configKey === "day_start_hour") {
                PluginService.setGlobalVar(pid, "cache", {});
                refreshCurrent();
            }
        }, 300);
    }

    // plugin setting key -> [config key, convert config value to the setting's type]
    readonly property var settingMap: ({
        "idleTimeout": ["idle_timeout", v => String(v)],
        "trackTitles": ["track_titles", v => !!v],
        "titleRetention": ["title_retention_days", v => String(v)],
        "dayStartHour": ["day_start_hour", v => String(v)]
    })
    property bool adopted: false

    function syncSettings() {
        if (!adopted)
            return;
        for (const key in settingMap)
            pushSetting(key, settingMap[key][0], pluginData[key]);
    }

    // Settings never touched in the plugin take their value from config.toml,
    // so the settings page shows what the daemon actually uses.
    function adoptConfig() {
        Proc.runCommand("screenTime.configGet", cliCommand(["config", "get"]), (stdout, exitCode) => {
            let cfg = null;
            try {
                cfg = exitCode === 0 ? JSON.parse(stdout) : null;
            } catch (e) {
                cfg = null;
            }
            if (cfg && pluginService) {
                for (const key in settingMap) {
                    const [configKey, convert] = settingMap[key];
                    if (pluginData[key] === undefined && cfg[configKey] !== undefined) {
                        const value = convert(cfg[configKey]);
                        pushed[key] = String(value);
                        pluginService.savePluginData(pid, key, value);
                    }
                }
            }
            adopted = true;
            syncSettings();
        }, 0);
    }

    onPluginDataChanged: syncSettings()

    // `dms ipc call screenTime toggle` / `dms ipc call screenTime open week`
    // e.g. for a niri keybind. Handled by the bar pill (see ScreenTimeWidget).
    IpcHandler {
        target: "screenTime"

        function toggle(): string {
            PluginService.setGlobalVar(root.pid, "openRequest", { t: Date.now(), kind: "", screen: "", toggle: true });
            return "ok";
        }

        function open(view: string): string {
            const kind = view === "week" ? "week" : "day";
            PluginService.setGlobalVar(root.pid, "openRequest", { t: Date.now(), kind: kind, screen: "", toggle: false });
            return "ok";
        }
    }

    Timer {
        interval: root.refreshMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refreshCurrent()
    }

    Component.onCompleted: adoptConfig()
}
