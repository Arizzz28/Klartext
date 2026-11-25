// The list of all tabs. Which ones a person sees depends on their rank (permission) - the server checks the same
// permission again on every request, so hiding a tab here is only for convenience, never for security.
import * as chats from "./pages/chats.js";
import * as groups from "./pages/groups.js";
import * as missions from "./pages/missions.js";
import * as calendar from "./pages/calendar.js";
import * as tasks from "./pages/tasks.js";
import * as notes from "./pages/notes.js";
import * as widgets from "./pages/widgets.js";
import * as search from "./pages/search.js";
import * as music from "./pages/music.js";
import * as visitors from "./pages/visitors.js";
import * as games from "./pages/games.js";
import * as forum from "./pages/forum.js";
import * as ai from "./pages/ai.js";
import * as whatsnew from "./pages/whatsnew.js";
import * as custom from "./pages/custom.js";
import * as profile from "./pages/profile.js";
import * as settings from "./pages/settings.js";
import * as admin from "./pages/admin.js";

export const TABS = [
  { id: "chats", label: "Chats", icon: "chats", page: chats },
  { id: "groups", label: "Groups", icon: "groups", page: groups },
  { id: "missions", label: "Missions", icon: "missions", page: missions, perm: "missions.use" },
  { id: "calendar", label: "Calendar", icon: "calendar", page: calendar, perm: "tabs.calendar" },
  { id: "tasks", label: "Tasks", icon: "tasks", page: tasks, perm: "tabs.tasks" },
  { id: "notes", label: "Notes", icon: "notes", page: notes, perm: "tabs.notes" },
  { id: "widgets", label: "Widgets", icon: "widgets", page: widgets, perm: "tabs.widgets" },
  { id: "search", label: "Search", icon: "search", page: search, perm: "tabs.search" },
  { id: "music", label: "Music", icon: "music", page: music, perm: "tabs.music" },
  { id: "visitors", label: "Visitors", icon: "visitors", page: visitors, perm: "tabs.visitors" },
  { id: "games", label: "Games", icon: "games", page: games, perm: "tabs.games" },
  { id: "forum", label: "Forum", icon: "forum", page: forum, perm: "tabs.forum" },
  { id: "ai", label: "AI", icon: "ai", page: ai, perm: "tabs.ai" },
  { id: "whatsnew", label: "What's new", icon: "whatsnew", page: whatsnew },
  { id: "custom", label: "My tabs", icon: "custom", page: custom, perm: "tabs.custom" },
  { id: "profile", label: "Profile", icon: "profile", page: profile },
  { id: "settings", label: "Settings", icon: "settings", page: settings },
  { id: "admin", label: "Admin", icon: "admin", page: admin, perm: "admin.access" },
];

// What the sidebar shows when the person has not chosen anything (or may not choose).
export const DEFAULT_PINNED = ["chats", "groups", "missions", "calendar", "tasks", "notes", "search", "games", "forum", "whatsnew", "profile", "settings", "admin"];

export const can = (me, perm) => !perm || (me.perms || []).includes(perm);
export const availableTabs = (me) => TABS.filter((t) => can(me, t.perm));

// The tabs in the sidebar: the person's own choice (needs tabs.editor) or the default, only what they may use.
export function pinnedTabs(me) {
  const all = availableTabs(me);
  const chosen = can(me, "tabs.editor") && Array.isArray(me.prefs?.tabs) ? me.prefs.tabs : DEFAULT_PINNED;
  const byId = new Map(all.map((t) => [t.id, t]));
  const out = chosen.map((id) => byId.get(id)).filter(Boolean);
  for (const must of ["settings"]) if (!out.some((t) => t.id === must)) out.push(byId.get(must));      // never lock yourself out of Settings
  return out;
}
