// TEMPLATE for a new page. Copy this file, e.g. to  frontend/pages/recipes.js , and change it.
// It is NOT used by the app until you add it to the list in frontend/tabs.js (see the steps in the README,
// section "Add a new page"). Nothing else needs to change for the page to show up in the navigation.
//
// What a page is: a file that exports  render({ list, main, arg, state })
//   main   an empty <div>: put the page into it
//   list   an empty <div> for a list on the left (only if the page exports  usesList = true, like Chats)
//   arg    the second part of the address:  #/recipes/42  ->  arg = "42"  (or null)
//   state  who is logged in:  state.me,  state.can("some.permission"),  state.config
// It may return a function; that function is called when the person leaves the page (stop timers there).
//
// SAFETY RULES (the tests check some of them):
//   - Build the page with h(...) and normal text. Never put data into innerHTML.
//   - Hiding a page here is only convenience. Every thing the page loads or saves goes through the server, and the
//     SERVER must check the permission again (backend: @perm_required("your.permission")).
import { get } from "../api.js";
import { emptyState, h } from "../ui.js";

export const usesList = false;

export async function render({ main, arg, state }) {
  // Example: load something from your own API route (see the README for the backend part).
  // const data = await get("/api/recipes");
  main.append(h("div", { class: "page" },
    h("h1", {}, "New page"),
    h("p", { class: "muted" }, `You are logged in as ${state.me.display_name}.`),
    arg ? h("p", {}, `Address part: ${arg}`) : null,
    emptyState("Nothing here yet", "Replace this with your content.")));
}
