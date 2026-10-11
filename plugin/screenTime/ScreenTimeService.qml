import QtQuick
import qs.Common
import qs.Services
import qs.Modules.Plugins

// Background surface (instantiated once): the only place that runs the
// `screentime` CLI. Results are published as plugin global vars so every bar
// pill, popout and desktop widget shares one fetch.
//
//   globalVars.screenTime.cache   { "<kind>:<date>": { data, fetchedAt } }  date "" = current
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
        const parts = key.split(":");
        const args = ["summary", "--range", parts[0], "--json"];
        if (parts[1])
            args.push("--date", parts[1]);
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
        return key.endsWith(":") ? 5000 : 600000;
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

    function syncSettings() {
        pushSetting("idleTimeout", "idle_timeout", pluginData.idleTimeout);
        pushSetting("trackTitles", "track_titles", pluginData.trackTitles);
        pushSetting("dayStartHour", "day_start_hour", pluginData.dayStartHour);
    }

    onPluginDataChanged: syncSettings()

    Timer {
        interval: root.refreshMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refreshCurrent()
    }

    Component.onCompleted: syncSettings()
}
