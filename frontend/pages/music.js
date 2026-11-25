// Music: playlists of LINKS to YouTube, SoundCloud, Spotify, Bandcamp, Apple Music ... Nothing is hosted or loaded
// from those services until you click a link, and the server only accepts links to those services.
import { del, get, post } from "../api.js";
import { act, confirmDialog, emptyState, field, h } from "../ui.js";

export const usesList = false;

export async function render({ main }) {
  const page = h("div", { class: "page wide" }, h("h1", {}, "Music"));
  const box = h("div");
  const name = h("input", { class: "input", maxlength: "60", required: true, placeholder: "New playlist" });
  const vis = h("select", { class: "input" }, [["private", "Only me"], ["everyone", "Everybody can see it"]].map(([v, l]) => h("option", { value: v }, l)));
  page.append(h("p", { class: "muted" }, "Collect links to songs on legal streaming services. Clicking a link opens the song on that service in a new tab."),
    h("section", { class: "card" }, h("form", { class: "inline-form", onSubmit: async (e) => { e.preventDefault(); if (await act(post("/api/playlists", { name: name.value, visibility: vis.value }), load)) name.value = ""; } },
      name, vis, h("button", { class: "btn primary", type: "submit" }, "Create playlist"))), box);
  main.append(page);

  async function load() {
    const lists = await get("/api/playlists");
    box.replaceChildren(...(lists.length ? lists.map((p) => {
      const title = h("input", { class: "input", placeholder: "Song title", maxlength: "120", required: true });
      const url = h("input", { class: "input", type: "url", placeholder: "https://…", required: true });
      return h("section", { class: "card" }, h("h2", {}, p.name, " ", h("span", { class: "tag" }, p.mine ? (p.visibility === "everyone" ? "shared" : "private") : `by @${p.owner}`)),
        p.tracks.length ? h("ul", { class: "rows" }, p.tracks.map((t) => h("li", { class: "row" },
          h("a", { class: "item-text", href: t.url, target: "_blank", rel: "noopener noreferrer" }, h("strong", {}, "▶ " + t.title), h("span", { class: "item-sub" }, new URL(t.url).hostname)),
          p.mine ? h("button", { class: "btn small danger-text", type: "button", onClick: () => act(del(`/api/playlists/${p.id}/tracks/${t.id}`), load) }, "Remove") : null))) : h("p", { class: "muted" }, "No songs yet."),
        p.mine ? h("form", { class: "inline-form", onSubmit: (e) => { e.preventDefault(); act(post(`/api/playlists/${p.id}/tracks`, { title: title.value, url: url.value }), load); } },
          title, url, h("button", { class: "btn small", type: "submit" }, "Add")) : null,
        p.mine ? h("button", { class: "btn small danger-text", type: "button", onClick: async () => { if (await confirmDialog("Delete playlist", `Delete “${p.name}”?`, "Delete", true)) act(del(`/api/playlists/${p.id}`), load); } }, "Delete playlist") : null);
    }) : [emptyState("No playlists yet")]));
  }
  await load();
}
