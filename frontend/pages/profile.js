// Your own profile: display name and picture.
import { get, patch, post } from "../api.js";
import { act, avatar, fileToAvatar, h, longDate, rankTag, toast } from "../ui.js";

export const usesList = false;

const STATUS_TEXT = { open: "waiting for an answer", accepted: "accepted", declined: "declined" };

async function offersCard(state) {
  const data = await get("/api/offers");
  const text = h("textarea", { class: "input", rows: "3", maxlength: "600", placeholder: "What can you offer? (help, an idea, a favour …)" });
  const card = h("section", { class: "card" }, h("h2", {}, "Pro offer"), h("p", { class: "muted" }, data.rules));
  if (data.enabled) {
    card.append(h("form", { onSubmit: async (e) => { e.preventDefault(); if (await act(post("/api/offers", { text: text.value }))) location.reload(); } }, text,
      h("button", { class: "btn primary", type: "submit" }, "Send offer")));
  }
  if (data.offers.length) card.append(h("ul", { class: "rows" }, data.offers.map((o) => h("li", { class: "row" },
    h("div", { class: "item-text" }, h("span", {}, o.text), h("span", { class: "item-sub" }, `${longDate(o.created)} · ${STATUS_TEXT[o.status]}${o.reward ? ` · reward: ${o.reward}` : ""}${o.answer ? ` · “${o.answer}”` : ""}`))))));
  return card;
}

export async function render({ main, state }) {
  const me = state.me;
  const pic = h("div", { class: "avatar-pick" });
  const name = h("input", { class: "input", maxlength: "40", required: true, value: me.display_name, id: "display-name" });
  const fileInput = h("input", { type: "file", accept: "image/*", hidden: true });

  const drawPic = () => pic.replaceChildren(avatar(state.me, "xl"));
  async function save(changes, okText) {
    try {
      state.me = await patch("/api/me", changes);
      state.onMeChanged();
      drawPic();
      toast(okText);
    } catch (e) { toast(e.message, "error"); }
  }

  fileInput.addEventListener("change", async () => {
    try { await save({ avatar: await fileToAvatar(fileInput.files[0]) }, "Photo updated."); }
    catch (e) { toast(e.message, "error"); }
  });
  drawPic();

  main.append(h("div", { class: "page" },
    h("h1", {}, "Your profile"),
    h("section", { class: "card" },
      h("div", { class: "avatar-row" }, pic,
        h("div", { class: "stack" },
          h("button", { class: "btn small", type: "button", onClick: () => fileInput.click() }, "Change photo"),
          h("button", { class: "btn small", type: "button", onClick: () => save({ avatar: "" }, "Photo removed.") }, "Remove photo"),
          fileInput)),
      h("form", {
        onSubmit: (e) => { e.preventDefault(); save({ display_name: name.value }, "Profile saved."); },
      },
        h("label", { class: "field", for: "display-name" }, h("span", { class: "field-label" }, "Display name"), name),
        h("button", { class: "btn primary", type: "submit" }, "Save changes"))),
    h("section", { class: "card" },
      h("dl", { class: "facts" },
        h("dt", {}, "Username"), h("dd", {}, "@" + me.username),
        h("dt", {}, "Email"), h("dd", {}, me.email),
        h("dt", {}, "Rank"), h("dd", {}, rankTag(me.rank), me.lease ? ` (rented: ${me.lease.rank.name} until ${longDate(me.lease.until)})` : ""),
        h("dt", {}, "Features"), h("dd", {}, `${me.perms.length} permissions in your rank`))),
    state.can("offers.create") ? await offersCard(state) : null));
}
