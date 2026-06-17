/**
 * HA Messenger — sidebar panel web component.
 *
 * Loaded by Home Assistant as a custom panel via async_register_panel().
 * Uses a vendored (offline) copy of Lit 3 at ./lit.js — no CDN calls.
 */
import { LitElement, html, css } from "./lit.js";

const MAX_CHARS = 140;
const AMBER_THRESHOLD = 120;
const PREVIEW_SETTLE_MS = 600;

class HaMessengerPanel extends LitElement {
  static properties = {
    hass: { type: Object },
    narrow: { type: Boolean },
    _message: { type: String, state: true },
    _channels: { type: Array, state: true },
    _devices: { type: Array, state: true },
    _selectedChannels: { type: Object, state: true },
    _selectedDevices: { type: Object, state: true },
    _previewUrl: { type: String, state: true },
    _previewing: { type: Boolean, state: true },
    _sending: { type: Boolean, state: true },
    _channelsLoaded: { type: Boolean, state: true },
    _error: { type: String, state: true },
  };

  static styles = css`
    :host {
      display: block;
      padding: 16px;
      max-width: 600px;
      margin: 0 auto;
      font-family: var(--paper-font-body1_-_font-family, sans-serif);
    }

    h1 {
      font-size: 1.4rem;
      margin: 0 0 20px;
      color: var(--primary-text-color);
    }

    .field-label {
      font-size: 0.85rem;
      font-weight: 500;
      color: var(--secondary-text-color);
      margin-bottom: 6px;
    }

    textarea {
      width: 100%;
      box-sizing: border-box;
      min-height: 90px;
      padding: 10px;
      border: 1px solid var(--divider-color, #e0e0e0);
      border-radius: 6px;
      font-size: 1rem;
      resize: vertical;
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color);
      font-family: inherit;
    }

    textarea:focus {
      outline: none;
      border-color: var(--primary-color, #03a9f4);
    }

    .char-counter {
      text-align: right;
      font-size: 0.8rem;
      color: var(--secondary-text-color);
      margin-top: 4px;
    }

    .char-counter.amber {
      color: var(--warning-color, #ff9800);
      font-weight: 600;
    }

    .recipients-section {
      margin-top: 16px;
    }

    .sub-label {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--secondary-text-color);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin: 10px 0 6px;
    }

    .chip-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 4px 10px;
      border-radius: 16px;
      font-size: 0.85rem;
      cursor: pointer;
      border: 1px solid var(--divider-color, #e0e0e0);
      background: var(--card-background-color, #fff);
      color: var(--primary-text-color);
      transition: background 0.15s, border-color 0.15s;
      user-select: none;
    }

    .chip.selected {
      background: var(--primary-color, #03a9f4);
      border-color: var(--primary-color, #03a9f4);
      color: #fff;
    }

    .chip:hover:not(.selected) {
      background: var(--secondary-background-color, #f5f5f5);
    }

    .empty-notice {
      font-size: 0.9rem;
      color: var(--secondary-text-color);
      font-style: italic;
    }

    .actions {
      display: flex;
      gap: 10px;
      margin-top: 20px;
    }

    button {
      padding: 8px 20px;
      border-radius: 6px;
      border: none;
      font-size: 0.95rem;
      cursor: pointer;
      font-family: inherit;
      transition: opacity 0.15s;
    }

    button:disabled {
      opacity: 0.4;
      cursor: not-allowed;
    }

    .btn-preview {
      background: var(--secondary-background-color, #f0f0f0);
      color: var(--primary-text-color);
      border: 1px solid var(--divider-color, #ccc);
    }

    .btn-send {
      background: var(--primary-color, #03a9f4);
      color: #fff;
    }

    .preview-area {
      margin-top: 20px;
    }

    .preview-area img {
      width: 100%;
      border-radius: 8px;
      border: 1px solid var(--divider-color, #e0e0e0);
    }

    .error-msg {
      margin-top: 12px;
      padding: 8px 12px;
      background: var(--error-color, #f44336);
      color: #fff;
      border-radius: 6px;
      font-size: 0.9rem;
    }
  `;

  constructor() {
    super();
    this._message = "";
    this._channels = [];
    this._devices = [];
    this._selectedChannels = new Set();
    this._selectedDevices = new Set();
    this._previewUrl = null;
    this._previewing = false;
    this._sending = false;
    this._channelsLoaded = false;
    this._error = null;
  }

  set hass(hass) {
    const prev = this._hass;
    this._hass = hass;
    this.requestUpdate("hass", prev);

    if (hass) {
      this._updateChannels(hass);
      this._refreshDevices(hass);
    }
  }

  get hass() {
    return this._hass;
  }

  _updateChannels(hass) {
    const channels = Object.keys(hass.states)
      .filter((entityId) => {
        if (!entityId.startsWith("camera.")) return false;
        const stateObj = hass.states[entityId];
        return stateObj && stateObj.attributes && stateObj.attributes.brand === "HA Messenger";
      })
      .map((entityId) => {
        const stateObj = hass.states[entityId];
        const friendlyName = stateObj.attributes.friendly_name || entityId;
        return {
          entity_id: entityId,
          name: friendlyName,
        };
      });

    const key = (arr) => arr.map((c) => c.entity_id).sort().join(",");
    if (key(this._channels) !== key(channels)) {
      const oldSelected = this._selectedChannels;
      const newEntityIds = new Set(channels.map((c) => c.entity_id));

      let nextSelected;
      if (!this._channelsLoaded || oldSelected.size === 0) {
        nextSelected = new Set(newEntityIds);
      } else {
        nextSelected = new Set([...oldSelected].filter((id) => newEntityIds.has(id)));
      }

      this._channels = channels;
      this._selectedChannels = nextSelected;
      this._channelsLoaded = true;
    }
  }

  _refreshDevices(hass) {
    const notifyServices = hass.services?.notify ?? {};
    const devices = Object.keys(notifyServices)
      .filter((k) => k.startsWith("mobile_app_"))
      .map((k) => ({
        service: k,
        name: k.replace("mobile_app_", "").replace(/_/g, " "),
      }));

    // Only update if list changed (avoid unnecessary re-renders). Sort before comparing
    // so API insertion-order changes don't trigger spurious updates.
    const key = (arr) => arr.map((d) => d.service).sort().join(",");
    if (key(this._devices) !== key(devices)) {
      // Remove any selected devices that no longer exist.
      const newServices = new Set(devices.map((d) => d.service));
      const pruned = new Set([...this._selectedDevices].filter((s) => newServices.has(s)));
      this._devices = devices;
      this._selectedDevices = pruned;
    }
  }

  get _canAct() {
    return this._message.trim().length > 0 && this._selectedChannels.size > 0;
  }

  get _isBusy() {
    return this._previewing || this._sending;
  }

  _onMessageInput(e) {
    this._message = e.target.value.slice(0, MAX_CHARS);
    this._previewUrl = null;
    this._error = null;
  }

  _toggleChannel(entityId) {
    const next = new Set(this._selectedChannels);
    next.has(entityId) ? next.delete(entityId) : next.add(entityId);
    this._selectedChannels = next;
  }

  _toggleDevice(service) {
    const next = new Set(this._selectedDevices);
    next.has(service) ? next.delete(service) : next.add(service);
    this._selectedDevices = next;
  }

  async _preview() {
    if (!this._canAct || this._previewing) return;
    this._previewing = true;
    this._error = null;
    try {
      const firstChannel = [...this._selectedChannels][0];
      await this._hass.callService(
        "ha_messenger",
        "send_message",
        { message: this._message, preview_only: true },
        { entity_id: firstChannel }
      );
      await new Promise((r) => setTimeout(r, PREVIEW_SETTLE_MS));
      const { path } = await this._hass.callWS({
        type: "auth/sign_path",
        path: "/api/camera_proxy/" + firstChannel,
        expires: 30,
      });
      if (!path) throw new Error("auth/sign_path returned no path");
      this._previewUrl = path;
    } catch (err) {
      this._error = "Preview failed: " + (err.message || String(err));
    } finally {
      this._previewing = false;
    }
  }

  async _send() {
    if (!this._canAct || this._sending) return;
    this._sending = true;
    this._error = null;
    try {
      // Single service call with all selected channels as targets so the backend fans
      // out to each channel and notify_targets fires exactly once (not once per channel).
      await this._hass.callService(
        "ha_messenger",
        "send_message",
        { message: this._message, notify_targets: [...this._selectedDevices] },
        { entity_id: [...this._selectedChannels] }
      );
      // Clear message on success.
      this._message = "";
      this._previewUrl = null;
    } catch (err) {
      this._error = "Send failed: " + (err.message || String(err));
    } finally {
      this._sending = false;
    }
  }

  render() {
    const charCount = this._message.length;
    const counterClass = charCount >= AMBER_THRESHOLD ? "char-counter amber" : "char-counter";
    const noChannels = this._channelsLoaded && this._channels.length === 0;

    return html`
      <h1>HA Messenger</h1>

      <div class="field-label">Message</div>
      <textarea
        maxlength=${MAX_CHARS}
        .value=${this._message}
        @input=${this._onMessageInput}
        placeholder="Type a message..."
      ></textarea>
      <div class=${counterClass}>${charCount}/${MAX_CHARS}</div>

      <div class="recipients-section">
        <div class="field-label">Recipients</div>

        <div class="sub-label">Channels</div>
        ${noChannels
          ? html`<div class="empty-notice">
              No HA Messenger channels found. Add one in Settings &rsaquo; Devices &amp; Services.
            </div>`
          : html`<div class="chip-list">
              ${this._channels.map(
                (ch) => html`
                  <span
                    class=${this._selectedChannels.has(ch.entity_id) ? "chip selected" : "chip"}
                    @click=${() => this._toggleChannel(ch.entity_id)}
                  >
                    ${ch.name}
                  </span>
                `
              )}
            </div>`}

        ${this._devices.length > 0
          ? html`
              <div class="sub-label">Devices</div>
              <div class="chip-list">
                ${this._devices.map(
                  (d) => html`
                    <span
                      class=${this._selectedDevices.has(d.service) ? "chip selected" : "chip"}
                      @click=${() => this._toggleDevice(d.service)}
                    >
                      ${d.name}
                    </span>
                  `
                )}
              </div>
            `
          : ""}
      </div>

      <div class="actions">
        <button
          class="btn-preview"
          ?disabled=${!this._canAct || this._isBusy}
          @click=${this._preview}
        >
          ${this._previewing ? "Loading..." : "Preview"}
        </button>
        <button
          class="btn-send"
          ?disabled=${!this._canAct || this._isBusy}
          @click=${this._send}
        >
          ${this._sending ? "Sending..." : "Send"}
        </button>
      </div>

      ${this._error ? html`<div class="error-msg">${this._error}</div>` : ""}

      ${this._previewUrl
        ? html`<div class="preview-area">
            <div class="field-label">Preview</div>
            <img src=${this._previewUrl} alt="Camera preview" />
          </div>`
        : ""}
    `;
  }
}

customElements.define("ha-messenger-panel", HaMessengerPanel);
