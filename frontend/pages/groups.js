// Group overview: invitations, your groups, open groups you can join, and the "new group" dialog.
import { get, post } from "../api.js";
import { avatar, emptyState, fileToAvatar, formatTime, h, icon, listItem, modal, toast } from "../ui.js";
import { renderGroupChat } from "./group_chat.js";

export const usesList = true;

export async function render({ list, main, arg, state }) {
  const body = h("div", { class: "items" });
  list.append(
    h("header", { class: "pane-head" },
      h("h1", {}, "Groups"),
      h("button", { class: "btn small", type: "button", onClick: openCreateDialog }, icon("plus"), "New group")),
    body);

  let destroyed = false;

  async function loadList() {
    try {
      const [invites, mine, open] = await Promise.all([get("/api/invitations"), get("/api/groups"), get("/api/groups/discover")]);
      if (destroyed) return;
      const items = [];

      if (invites.length) {
        items.push(h("h2", { class: "section-title" }, "Invitations"));
        for (const inv of invites) {
          items.push(h("div", { class: "invite" },
            avatar(inv.group),
            h("div", { class: "item-text" },
              h("strong", {}, inv.group.name),
              h("span", { class: "item-sub" }, `Invited by ${inv.from.display_name}`)),
            h("div", { class: "invite-actions" },
              h("button", { class: "btn small primary", type: "button", onClick: () => answer(inv, "accept") }, "Accept"),
              h("button", { class: "btn small", type: "button", onClick: () => answer(inv, "decline") }, "Decline"))));
        }
      }

      items.push(h("h2", { class: "section-title" }, "Your groups"));
      if (mine.length) {
        for (const gr of mine) {
          items.push(listItem({
            entity: gr, title: gr.name,
            subtitle: gr.last ? gr.last.text : `${gr.member_count} member${gr.member_count === 1 ? "" : "s"}`,
            time: gr.last ? formatTime(gr.last.ts) : "", href: `#/groups/${gr.id}`, active: arg === gr.id,
          }));
        }
      } else {
        items.push(emptyState("No groups yet", "Create one, or join an open group below."));
      }

      if (open.length) {
        items.push(h("h2", { class: "section-title" }, "Open groups"));
        for (const gr of open) {
          items.push(h("div", { class: "invite" },
            avatar(gr),
            h("div", { class: "item-text" },
              h("strong", {}, gr.name),
              h("span", { class: "item-sub" }, `${gr.member_count} member${gr.member_count === 1 ? "" : "s"}`)),
            h("button", { class: "btn small", type: "button", onClick: () => join(gr) }, "Join")));
        }
      }
      body.replaceChildren(...items);
    } catch (e) {
      if (!destroyed) body.replaceChildren(emptyState("Couldn't load groups", e.message));
    }
  }

  async function answer(inv, action) {
    try {
      const res = await post(`/api/invitations/${inv.id}/${action}`);
      state.refreshInvites();
      if (action === "accept") location.hash = `#/groups/${res.group_id}`;
      else loadList();
    } catch (e) { toast(e.message, "error"); loadList(); }
  }

  async function join(gr) {
    try {
      await post(`/api/groups/${gr.id}/join`);
      location.hash = `#/groups/${gr.id}`;
    } catch (e) { toast(e.message, "error"); loadList(); }
  }

  function openCreateDialog() {
    let avatarData = "";
    const name = h("input", { class: "input", maxlength: "40", required: true, placeholder: "Group name" });
    const desc = h("textarea", { class: "input", maxlength: "200", rows: "2", placeholder: "What is this group about? (optional)" });
    const preview = h("div", { class: "avatar-pick" }, avatar({ name: "?" }, "lg"));
    const fileInput = h("input", { type: "file", accept: "image/*", hidden: true });
    fileInput.addEventListener("change", async () => {
      try {
        avatarData = await fileToAvatar(fileInput.files[0]);
        preview.replaceChildren(avatar({ avatar: avatarData, name: "?" }, "lg"));
      } catch (e) { toast(e.message, "error"); }
    });
    const mode = (value, title, text, checked) => h("label", { class: "choice" },
      h("input", { type: "radio", name: "join_mode", value, checked }),
      h("span", {}, h("strong", {}, title), h("small", {}, text)));
    const modeOpen = mode("open", "Open", "Anyone with an account can join.", false);
    const modeInvite = mode("invite_only", "Invite-only", "Only people invited by a group admin can join.", true);
    const msg = h("p", { class: "form-msg", role: "alert" });
    const submit = h("button", { class: "btn primary", type: "submit" }, "Create group");

    const form = h("form", { class: "dialog-body" },
      h("div", { class: "avatar-row" }, preview,
        h("button", { class: "btn small", type: "button", onClick: () => fileInput.click() }, "Choose image"), fileInput),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Name"), name),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Description"), desc),
      h("fieldset", { class: "choices" }, h("legend", { class: "field-label" }, "Who can join?"), modeInvite, modeOpen),
      msg, h("div", { class: "dialog-actions" }, submit));
    const box = modal("New group", form);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      submit.disabled = true;
      try {
        const created = await post("/api/groups", {
          name: name.value, description: desc.value, avatar: avatarData,
          join_mode: form.querySelector("input[name=join_mode]:checked").value,
        });
        box.close();
        location.hash = `#/groups/${created.id}`;
      } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; submit.disabled = false; }
    });
  }

  loadList();
  const timer = setInterval(loadList, 10000);
  let closeChat = null;
  if (arg) closeChat = await renderGroupChat({ main, id: arg, state, onChanged: loadList });
  else main.append(emptyState("Pick a group", "Choose a group on the left, or create a new one."));

  return () => { destroyed = true; clearInterval(timer); if (closeChat) closeChat(); };
}
