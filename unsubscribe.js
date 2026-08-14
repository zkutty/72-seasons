"use strict";

const endpoint = "https://subscribe.ko-72.com";
const token = new URLSearchParams(location.hash.slice(1)).get("token");
const requestView = document.getElementById("request-view");
const confirmView = document.getElementById("confirm-view");

if (token) {
  // Remove the bearer token from visible browser history immediately. It
  // remains only in this page's local variable so a transient retry works.
  history.replaceState(null, "", location.pathname);
  requestView.hidden = true;
  confirmView.hidden = false;
}

document.getElementById("request-form").addEventListener("submit", async function (event) {
  event.preventDefault();
  const email = document.getElementById("email").value;
  const button = this.querySelector("button");
  document.getElementById("request-error").hidden = true;
  button.disabled = true;
  button.textContent = "…";
  try {
    const response = await fetch(`${endpoint}/unsubscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, language: document.body.dataset.language }),
    });
    if (!response.ok) throw new Error("Request failed");
    this.hidden = true;
    document.getElementById("request-success").hidden = false;
  } catch {
    button.disabled = false;
    button.textContent = button.dataset.label;
    document.getElementById("request-error").hidden = false;
  }
});

document.getElementById("confirm-form").addEventListener("submit", async function (event) {
  event.preventDefault();
  const button = this.querySelector("button");
  document.getElementById("confirm-error").hidden = true;
  button.disabled = true;
  button.textContent = "…";
  try {
    const response = await fetch(`${endpoint}/unsubscribe/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!response.ok) throw new Error("Confirmation failed");
    this.hidden = true;
    document.getElementById("confirm-success").hidden = false;
  } catch {
    button.disabled = false;
    button.textContent = button.dataset.label;
    document.getElementById("confirm-error").hidden = false;
    requestView.hidden = false;
  }
});
