APP_JS_PATH = "/static/js/app.js"
SETTINGS_JS_PATH = "/static/js/settings.js"
SKILLS_MEMORY_JS_PATH = "/static/js/skills_memory.js"
PANELS_JS_PATH = "/static/js/panels.js"
NEXUS_JS_PATH = "/static/js/nexus.js"

MOVED_NEXUS_DISPLAY_HELPER_FUNCTION_DEFINITIONS = (
    "function updateNexusJobBanner",
    "function renderNexusDocumentDetail",
    "function renderNexusTimeline",
    "function pushNexusTimelineEvent",
    "function renderNexusDocuments",
    "function renderNexusJobs",
    "function setNexusDropzoneActive",
)
MOVED_NEXUS_DISPLAY_HELPER_WINDOW_EXPORTS = (
    "window.updateNexusJobBanner = updateNexusJobBanner",
    "window.renderNexusDocumentDetail = renderNexusDocumentDetail",
    "window.renderNexusTimeline = renderNexusTimeline",
    "window.pushNexusTimelineEvent = pushNexusTimelineEvent",
    "window.renderNexusDocuments = renderNexusDocuments",
    "window.renderNexusJobs = renderNexusJobs",
    "window.setNexusDropzoneActive = setNexusDropzoneActive",
)

NEXUS_DISPLAY_HELPER_GLOBAL_DEPENDENCY_TOKENS = (
    ("function esc", "const esc", "window.esc"),
    ("function formatBytes", "const formatBytes", "window.formatBytes"),
    ("nexusEventTimeline",),
    ("nexusSelectedDocumentId",),
    ("function selectNexusDocument", "async function selectNexusDocument"),
    ("function downloadNexusDocument", "async function downloadNexusDocument"),
    (
        "function downloadNexusExtractedText",
        "async function downloadNexusExtractedText",
    ),
    ("function deleteNexusDocument", "async function deleteNexusDocument"),
)

MOVED_SKILLS_AND_MEMORY_FUNCTION_DEFINITIONS = (
    "function showTaskOptions",
    "async function chooseTaskOption",
    "async function refreshSkills",
    "function renderSkills",
    "async function deleteSkill",
    "async function refreshMemory",
    "async function searchMemory",
    "function renderMemory",
    "async function deleteMemory",
    "function showAddMemoryForm",
    "function hideAddMemoryForm",
    "async function saveNewMemory",
    "async function editMemoryInline",
)
MOVED_SKILLS_AND_MEMORY_STATE_TOKENS = (
    "var _taskOptionsMap",
    "var _memSearchTimer",
    "var _catColor",
    "var _catLabel",
)
MOVED_SKILLS_AND_MEMORY_WINDOW_EXPORTS = (
    "window.showTaskOptions = showTaskOptions",
    "window.chooseTaskOption = chooseTaskOption",
    "window._taskOptionsMap = _taskOptionsMap",
    "window.refreshSkills = refreshSkills",
    "window.renderSkills = renderSkills",
    "window.deleteSkill = deleteSkill",
    "window.refreshMemory = refreshMemory",
    "window.searchMemory = searchMemory",
    "window.renderMemory = renderMemory",
    "window.deleteMemory = deleteMemory",
    "window.showAddMemoryForm = showAddMemoryForm",
    "window.hideAddMemoryForm = hideAddMemoryForm",
    "window.saveNewMemory = saveNewMemory",
    "window.editMemoryInline = editMemoryInline",
    "window._memSearchTimer = _memSearchTimer",
    "window._catColor = _catColor",
    "window._catLabel = _catLabel",
)
MOVED_SETTINGS_MODAL_FUNCTION_DEFINITIONS = (
    "function openSettings",
    "function closeSettings",
)
MOVED_SETTINGS_MODAL_WINDOW_EXPORTS = (
    "window.openSettings = openSettings",
    "window.closeSettings = closeSettings",
)
MOVED_SETTINGS_UI_HELPER_FUNCTION_DEFINITIONS = (
    "function applyOrchFeatureModeUi",
    "function updateCtxLabel",
    "function applySearchUI",
    "function applyStreamingUI",
)
MOVED_SETTINGS_UI_HELPER_WINDOW_EXPORTS = (
    "window.applyOrchFeatureModeUi = applyOrchFeatureModeUi",
    "window.updateCtxLabel = updateCtxLabel",
    "window.applySearchUI = applySearchUI",
    "window.applyStreamingUI = applyStreamingUI",
)
MOVED_SETTINGS_TAB_FUNCTION_DEFINITIONS = (
    "function switchTab",
)
MOVED_SETTINGS_TAB_WINDOW_EXPORTS = (
    "window.switchTab = switchTab",
)

SWITCH_TAB_GLOBAL_DEPENDENCY_TOKENS = (
    ("function _setPanelTabActiveButton",),
    ("function refreshFileBrowser", "async function refreshFileBrowser"),
    ("function refreshProjectFileManager", "async function refreshProjectFileManager"),
    ("function refreshSkills", "async function refreshSkills"),
    ("function refreshMemory", "async function refreshMemory"),
    ("function refreshModelDb", "async function refreshModelDb"),
    ("function refreshModelRoles", "async function refreshModelRoles"),
    ("function refreshEchoVault", "async function refreshEchoVault"),
    ("function refreshAsrTab", "async function refreshAsrTab"),
    ("function refreshTtsTab", "async function refreshTtsTab"),
)

OPEN_SETTINGS_GLOBAL_DEPENDENCY_TOKENS = (
    ("function loadSettingsFromDb", "async function loadSettingsFromDb"),
    ("function loadOrchestrationSettings", "async function loadOrchestrationSettings"),
    ("function loadGhRepoConfig", "async function loadGhRepoConfig"),
    ("function refreshEnsembleVramStatus", "async function refreshEnsembleVramStatus"),
    ("ensembleVramTimer",),
    ("function _ttsInitSettingsUI", "async function _ttsInitSettingsUI"),
    ("function _echoInitSettingsUI", "async function _echoInitSettingsUI"),
    ("function applyUiFontSettings", "async function applyUiFontSettings"),
)
SETTINGS_UI_HELPER_GLOBAL_DEPENDENCY_TOKENS = (
    ("searchEnabled",),
    ("streamingEnabled",),
    ("function saveEnsembleSettings", "async function saveEnsembleSettings"),
    (
        "function refreshEnsembleVramStatus",
        "async function refreshEnsembleVramStatus",
    ),
)
