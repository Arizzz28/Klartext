// Upload a file straight into the object storage (the server only hands out a signed link).
import { del, post } from "./api.js";

// Returns { promise, cancel }. promise resolves with the finished attachment {id, name, mime, size, kind, url}.
export function uploadFile(file, { kind = "attachment", chatType, chatKey, onProgress = () => {} } = {}) {
  let xhr = null;
  let cancelled = false;
  let attachmentId = null;

  const promise = (async () => {
    const start = await post("/api/uploads", {
      filename: file.name, mime: file.type || "application/octet-stream", size: file.size,
      kind, chat_type: chatType, chat_key: chatKey,
    });
    attachmentId = start.id;
    if (cancelled) throw new Error("Cancelled");
    await new Promise((resolve, reject) => {
      xhr = new XMLHttpRequest();
      xhr.open("PUT", start.upload_url);
      for (const [name, value] of Object.entries(start.headers || {})) xhr.setRequestHeader(name, value);
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
      xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`The storage refused the file (${xhr.status}).`)));
      xhr.onerror = () => reject(new Error("The upload failed. Check your connection."));
      xhr.onabort = () => reject(new Error("Cancelled"));
      xhr.send(file);
    });
    return post(`/api/uploads/${start.id}/confirm`);
  })();

  return {
    promise,
    cancel() {
      cancelled = true;
      if (xhr) xhr.abort();
      if (attachmentId) del(`/api/uploads/${attachmentId}`).catch(() => {});
    },
  };
}
