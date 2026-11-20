// One group: messages, member list, group info and (for admins) management tools.
import { get, patch, post } from "../api.js";
import { createChatPane } from "../chatpane.js";
import { avatar, confirmDialog, emptyState, fileToAvatar, h, icon, modal, toast } from "../ui.js";

export async function renderGroupChat({ main, id, state, onChanged }) {
  const base = `/api/groups/${encodeURIComponent(id)}`;
  let group;
  try {
    group = await get(base);
  } catch (e) {
    main.append(h("div", { class: "chat-head" }, h("a", { class: "icon-btn back", href: "#/groups", "aria-label": "Back to groups" }, icon("back"))),
      emptyState("Can't open this group", e.message));
    return () => {};
  }

  const people = new Map();
  const isAdmin = () => group.role === "admin";
  const indexPeople = () => { people.clear(); group.members.forEach((m) => people.set(m.username, m)); };
  indexPeople();

  const header = h("header", { class: "chat-head" });
  const aside = h("aside", { class: "info", "aria-label": "Group info" });
  let layout;

  function fillHeader() {
    header.replaceChildren(
      h("a", { class: "icon-btn back", href: "#/groups", "aria-label": "Back to groups" }, icon("back")),
      avatar(group),
      h("div", { class: "chat-title" },
        h("strong", {}, group.name),
        h("span", { class: "muted" }, `${group.member_count} member${group.member_count === 1 ? "" : "s"}`)),
      h("button", { class: "icon-btn info-toggle", type: "button", "aria-label": "Group info", onClick: () => layout.classList.toggle("info-open") }, icon("info")));
  }

  const pane = createChatPane({
    me: state.me, header,
    getUser: (username) => people.get(username) || { display_name: username },
    load: (after) => get(`${base}/messages?after=${after}`),
    send: (text) => post(`${base}/messages`, { text }),
    onSent: onChanged,
  });
  layout = h("div", { class: "group-layout" }, pane.root, aside);
  main.append(layout);

  async function act(promise, okText) {
    try {
      const res = await promise;
      if (okText || res?.message) toast(okText || res.message);
      await refresh();
    } catch (e) { toast(e.message, "error"); }
  }

  function memberRow(m) {
    const actions = [];
    if (isAdmin() && m.username !== state.me.username) {
      if (m.role !== "admin") {
        actions.push(h("button", { class: "btn small", type: "button", onClick: () => act(post(`${base}/members/${encodeURIComponent(m.username)}/promote`)) }, "Make admin"));
      }
      actions.push(h("button", {
        class: "btn small danger-text", type: "button",
        onClick: async () => {
          if (await confirmDialog("Remove member", `Remove ${m.display_name} from this group?`, "Remove", true)) {
            act(post(`${base}/members/${encodeURIComponent(m.username)}/remove`));
          }
        },
      }, "Remove"));
    }
    return h("li", { class: "member" },
      avatar(m, "sm"),
      h("div", { class: "item-text" },
        h("strong", {}, m.display_name, m.username === state.me.username ? " (you)" : ""),
        m.role === "admin" ? h("span", { class: "tag" }, "Admin") : null),
      actions.length ? h("div", { class: "member-actions" }, actions) : null);
  }

  function inviteForm() {
    const input = h("input", { class: "input", type: "text", list: "invite-users", placeholder: "Username", "aria-label": "Username to invite", autocomplete: "off" });
    const datalist = h("datalist", { id: "invite-users" });
    get("/api/users").then((users) => {
      const inGroup = new Set(group.members.map((m) => m.username));
      users.filter((u) => !inGroup.has(u.username)).forEach((u) => datalist.append(h("option", { value: u.username }, u.display_name)));
    }).catch(() => {});
    return h("form", {
      class: "invite-form",
      onSubmit: async (e) => {
        e.preventDefault();
        const name = input.value.trim();
        if (!name) return;
        try {
          const res = await post(`${base}/invitations`, { username: name });
          toast(res.message);
          input.value = "";
        } catch (err) { toast(err.message, "error"); }
      },
    }, input, datalist, h("button", { class: "btn small primary", type: "submit" }, "Invite"));
  }

  function openEditDialog() {
    let avatarData = group.avatar;
    const name = h("input", { class: "input", maxlength: "40", required: true, value: group.name });
    const desc = h("textarea", { class: "input", maxlength: "200", rows: "2" });
    desc.value = group.description;
    const preview = h("div", { class: "avatar-pick" }, avatar({ ...group, avatar: avatarData }, "lg"));
    const fileInput = h("input", { type: "file", accept: "image/*", hidden: true });
    fileInput.addEventListener("change", async () => {
      try {
        avatarData = await fileToAvatar(fileInput.files[0]);
        preview.replaceChildren(avatar({ name: group.name, avatar: avatarData }, "lg"));
      } catch (e) { toast(e.message, "error"); }
    });
    const msg = h("p", { class: "form-msg", role: "alert" });
    const form = h("form", { class: "dialog-body" },
      h("div", { class: "avatar-row" }, preview,
        h("button", { class: "btn small", type: "button", onClick: () => fileInput.click() }, "Change image"),
        h("button", { class: "btn small", type: "button", onClick: () => { avatarData = ""; preview.replaceChildren(avatar({ name: group.name }, "lg")); } }, "Remove image"),
        fileInput),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Name"), name),
      h("label", { class: "field" }, h("span", { class: "field-label" }, "Description"), desc),
      msg, h("div", { class: "dialog-actions" }, h("button", { class: "btn primary", type: "submit" }, "Save changes")));
    const box = modal("Edit group", form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await patch(base, { name: name.value, description: desc.value, avatar: avatarData });
        box.close();
        toast("Group updated.");
        await refresh();
        onChanged();
      } catch (err) { msg.textContent = err.message; msg.className = "form-msg error"; }
    });
  }

  async function leave() {
    if (!(await confirmDialog("Leave group", `Leave “${group.name}”?`, "Leave group", true))) return;
    try {
      await post(`${base}/leave`);
      toast("You left the group.");
      onChanged();
      location.hash = "#/groups";
    } catch (e) { toast(e.message, "error"); }
  }

  function renderInfo() {
    aside.replaceChildren(
      h("div", { class: "info-top" },
        h("button", { class: "icon-btn info-close", type: "button", "aria-label": "Close group info", onClick: () => layout.classList.remove("info-open") }, icon("close"))),
      h("div", { class: "info-head" },
        avatar(group, "lg"),
        h("h2", {}, group.name),
        group.description ? h("p", { class: "muted" }, group.description) : null,
        h("span", { class: "tag" }, group.join_mode === "open" ? "Open group" : "Invite-only")),
      isAdmin() ? h("button", { class: "btn small block", type: "button", onClick: openEditDialog }, "Edit group") : null,
      h("h3", { class: "section-title" }, `Members (${group.member_count})`),
      h("ul", { class: "members" }, group.members.map(memberRow)),
      isAdmin() ? h("div", {}, h("h3", { class: "section-title" }, "Invite someone"), inviteForm()) : null,
      h("button", { class: "btn danger block leave", type: "button", onClick: leave }, "Leave group"));
  }

  async function refresh() {
    try {
      group = await get(base);
    } catch (e) {
      if (e.status === 403 || e.status === 404) {          // removed from the group, or the group is gone
        toast("You are no longer in this group.", "error");
        onChanged();
        location.hash = "#/groups";
      }
      return;
    }
    indexPeople();
    fillHeader();
    renderInfo();
    onChanged();
  }

  fillHeader();
  renderInfo();
  pane.focus();
  const timer = setInterval(refresh, 10000);
  return () => { clearInterval(timer); pane.destroy(); };
}
