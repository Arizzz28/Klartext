// Your own profile: display name and picture.
import { patch } from "../api.js";
import { avatar, fileToAvatar, h, toast } from "../ui.js";

export const usesList = false;

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
        h("dt", {}, "Email"), h("dd", {}, me.email)))));
}
