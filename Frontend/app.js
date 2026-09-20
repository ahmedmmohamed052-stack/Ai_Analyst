const API_BASE = ""; // same-origin; change if the API is hosted elsewhere

// ── i18n helpers (engine lives in i18n.js, strings in i18n-app.js) ─────
const t = (key, vars) => I18N.t(key, vars);
// Backend errors come back as English `detail` strings — translate when we can.
const apiError = (body, fallbackKey) => (body && body.detail ? I18N.tError(body.detail) : t(fallbackKey));
// Escape anything user-supplied before it goes into innerHTML.
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const planLabel = (planId, fallback) => {
  const key = "plan." + planId;
  const label = t(key);
  return label === key ? (fallback || planId) : label;
};

// ── Elements ────────────────────────────────────────────────────────────
const authScreen = document.getElementById("auth-screen");
const appScreen = document.getElementById("app-screen");

const tabLogin = document.getElementById("tab-login");
const tabSignup = document.getElementById("tab-signup");
const loginForm = document.getElementById("login-form");
const signupForm = document.getElementById("signup-form");
const otpForm = document.getElementById("otp-form");
const forgotForm = document.getElementById("forgot-form");

const loginEmail = document.getElementById("login-email");
const loginPassword = document.getElementById("login-password");
const loginBtn = document.getElementById("login-btn");
const loginError = document.getElementById("login-error");
const forgotBtn = document.getElementById("forgot-btn");

const signupName = document.getElementById("signup-name");
const signupEmail = document.getElementById("signup-email");
const signupPassword = document.getElementById("signup-password");
const signupBtn = document.getElementById("signup-btn");
const signupError = document.getElementById("signup-error");

const googleBtn = document.getElementById("google-btn");
const appleBtn = document.getElementById("apple-btn");

const otpEmailTarget = document.getElementById("otp-email-target");
const otpDigits = Array.from(document.querySelectorAll(".otp-digit"));
const otpVerifyBtn = document.getElementById("otp-verify-btn");
const otpResendBtn = document.getElementById("otp-resend-btn");
const otpSkipBtn = document.getElementById("otp-skip-btn");
const otpError = document.getElementById("otp-error");

const forgotEmail = document.getElementById("forgot-email");
const forgotSendBtn = document.getElementById("forgot-send-btn");
const forgotBackBtn = document.getElementById("forgot-back-btn");
const forgotNote = document.getElementById("forgot-note");

const logoutBtn = document.getElementById("logout-btn");
const subscriptionBadge = document.getElementById("subscription-badge");
const verifyNudge = document.getElementById("verify-nudge");
const userAvatar = document.getElementById("user-avatar");

const billingGate = document.getElementById("billing-gate");
const plansGrid = document.getElementById("plans-grid");
const billingError = document.getElementById("billing-error");

const teamSection = document.getElementById("team-section");
const teamSeatsLabel = document.getElementById("team-seats-label");
const teamMemberList = document.getElementById("team-member-list");
const teamInviteEmail = document.getElementById("team-invite-email");
const teamInviteBtn = document.getElementById("team-invite-btn");
const teamError = document.getElementById("team-error");

const analysisArea = document.getElementById("analysis-area");
const datasetList = document.getElementById("dataset-list");
const datasetPicker = document.getElementById("dataset-picker");
const showUploadBtn = document.getElementById("show-upload-btn");
const showConnectBtn = document.getElementById("show-connect-btn");
const uploadForm = document.getElementById("upload-form");
const connectForm = document.getElementById("connect-form");
const uploadName = document.getElementById("upload-name");
const uploadFile = document.getElementById("upload-file");
const uploadSubmitBtn = document.getElementById("upload-submit-btn");
const uploadCancelBtn = document.getElementById("upload-cancel-btn");
const uploadError = document.getElementById("upload-error");
const connectName = document.getElementById("connect-name");
const connectType = document.getElementById("connect-type");
const connectHost = document.getElementById("connect-host");
const connectPort = document.getElementById("connect-port");
const connectDb = document.getElementById("connect-db");
const connectUser = document.getElementById("connect-user");
const connectPassword = document.getElementById("connect-password");
const connectSubmitBtn = document.getElementById("connect-submit-btn");
const connectCancelBtn = document.getElementById("connect-cancel-btn");
const connectError = document.getElementById("connect-error");
const questionInput = document.getElementById("question-input");
const askBtn = document.getElementById("ask-btn");
const askError = document.getElementById("ask-error");
const loading = document.getElementById("loading");
const resultsSection = document.getElementById("results");
const resultsContent = document.getElementById("results-content");
const downloadPdfBtn = document.getElementById("download-pdf-btn");
const improveBtn = document.getElementById("improve-btn");
const historyList = document.getElementById("history-list");
const followupChip = document.getElementById("followup-chip");
const followupClear = document.getElementById("followup-clear");

let currentReportId = null;
let followUpFromReportId = null;
let pendingVerifyEmail = null;

// ── Token storage ──────────────────────────────────────────────────────
const getToken = () => localStorage.getItem("ai_analyst_token");
const setToken = (t) => localStorage.setItem("ai_analyst_token", t);
const clearToken = () => localStorage.removeItem("ai_analyst_token");
const authHeaders = () => {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
};

// ── Screen switching ───────────────────────────────────────────────────
function showAuth() {
  appScreen.classList.add("hidden");
  authScreen.classList.remove("hidden");
  showAuthStep("login");
}

function showApp() {
  authScreen.classList.add("hidden");
  appScreen.classList.remove("hidden");
  refreshAccountState();
}

function showAuthStep(step) {
  loginForm.classList.toggle("hidden", step !== "login");
  signupForm.classList.toggle("hidden", step !== "signup");
  otpForm.classList.toggle("hidden", step !== "otp");
  forgotForm.classList.toggle("hidden", step !== "forgot");
  document.querySelector(".social-row").classList.toggle("hidden", step === "otp" || step === "forgot");
  document.querySelector(".divider").classList.toggle("hidden", step === "otp" || step === "forgot");
  document.querySelector(".tabs").classList.toggle("hidden", step === "otp" || step === "forgot");
}

tabLogin.addEventListener("click", () => {
  tabLogin.classList.add("active");
  tabSignup.classList.remove("active");
  showAuthStep("login");
});
tabSignup.addEventListener("click", () => {
  tabSignup.classList.add("active");
  tabLogin.classList.remove("active");
  showAuthStep("signup");
});
forgotBtn.addEventListener("click", () => showAuthStep("forgot"));
forgotBackBtn.addEventListener("click", () => showAuthStep("login"));

// ── Password auth ──────────────────────────────────────────────────────
async function login() {
  loginError.textContent = "";
  const email = loginEmail.value.trim();
  const password = loginPassword.value;
  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(email ? { email, password } : { password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.login_failed"));
    }
    const data = await res.json();
    setToken(data.access_token);
    showApp();
  } catch (e) {
    loginError.textContent = e.message;
  }
}

async function signup() {
  signupError.textContent = "";
  const full_name = signupName.value.trim();
  const email = signupEmail.value.trim();
  const password = signupPassword.value;
  if (password.length < 8) {
    signupError.textContent = t("msg.pw_short");
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, full_name }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.signup_failed"));
    }
    const data = await res.json();
    setToken(data.access_token);
    pendingVerifyEmail = email;
    otpEmailTarget.textContent = email;
    otpDigits.forEach((d) => (d.value = ""));
    otpError.textContent = "";
    showAuthStep("otp");
    otpDigits[0].focus();
  } catch (e) {
    signupError.textContent = e.message;
  }
}

function logout() {
  clearToken();
  currentReportId = null;
  followUpFromReportId = null;
  showAuth();
}

loginBtn.addEventListener("click", login);
signupBtn.addEventListener("click", signup);
logoutBtn.addEventListener("click", logout);
[loginEmail, loginPassword].forEach((el) => el.addEventListener("keydown", (e) => { if (e.key === "Enter") login(); }));
[signupName, signupEmail, signupPassword].forEach((el) => el.addEventListener("keydown", (e) => { if (e.key === "Enter") signup(); }));

// ── Forgot password ────────────────────────────────────────────────────
forgotSendBtn.addEventListener("click", async () => {
  forgotNote.textContent = "";
  const email = forgotEmail.value.trim();
  if (!email) return;
  await fetch(`${API_BASE}/auth/request-password-reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  forgotNote.textContent = t("msg.reset_sent");
});

// ── Email verification (6-digit code) ──────────────────────────────────
otpDigits.forEach((input, i) => {
  input.addEventListener("input", () => {
    input.value = input.value.replace(/\D/g, "").slice(0, 1);
    if (input.value && i < otpDigits.length - 1) otpDigits[i + 1].focus();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && !input.value && i > 0) otpDigits[i - 1].focus();
  });
  input.addEventListener("paste", (e) => {
    const text = (e.clipboardData || window.clipboardData).getData("text").replace(/\D/g, "");
    if (text.length) {
      e.preventDefault();
      text.split("").slice(0, otpDigits.length).forEach((ch, idx) => { otpDigits[idx].value = ch; });
      otpDigits[Math.min(text.length, otpDigits.length) - 1].focus();
    }
  });
});

async function verifyOtp() {
  otpError.textContent = "";
  const code = otpDigits.map((d) => d.value).join("");
  if (code.length !== 6) {
    otpError.textContent = t("msg.otp_incomplete");
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/auth/verify-email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: pendingVerifyEmail, code }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.otp_bad"));
    }
    showApp();
  } catch (e) {
    otpError.textContent = e.message;
  }
}

otpVerifyBtn.addEventListener("click", verifyOtp);
otpSkipBtn.addEventListener("click", showApp);
otpResendBtn.addEventListener("click", async () => {
  otpError.textContent = "";
  const res = await fetch(`${API_BASE}/auth/resend-verification`, {
    method: "POST",
    headers: authHeaders(),
  });
  otpError.textContent = res.ok ? t("msg.otp_resent") : t("msg.otp_resend_fail");
});

// ── Google / Apple sign-in (via Firebase, see firebase-init.js) ───────
async function socialSignIn(getIdToken, button) {
  loginError.textContent = "";
  button.disabled = true;
  try {
    if (!window.firebaseAuthReady) {
      throw new Error(t("msg.social_loading"));
    }
    const idToken = await getIdToken();
    const res = await fetch(`${API_BASE}/auth/firebase`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.social_failed"));
    }
    const data = await res.json();
    setToken(data.access_token);
    showApp();
  } catch (e) {
    loginError.textContent = e.message || t("msg.social_cancelled");
  } finally {
    button.disabled = false;
  }
}

googleBtn.addEventListener("click", () => socialSignIn(() => window.signInWithGoogle(), googleBtn));
appleBtn.addEventListener("click", () => socialSignIn(() => window.signInWithApple(), appleBtn));

// ── Account state / billing gate ──────────────────────────────────────
async function refreshAccountState() {
  const res = await fetch(`${API_BASE}/me`, { headers: authHeaders() });
  if (res.status === 401) {
    logout();
    return;
  }
  const me = await res.json();

  if (me.photo_url) {
    userAvatar.src = me.photo_url;
    userAvatar.classList.remove("hidden");
  } else {
    userAvatar.classList.add("hidden");
  }

  if (me.is_owner || me.subscription) {
    const isTeamMember = me.team_role === "member";
    const isTrial = me.subscription && me.subscription.status === "trial";
    let daysLeft = null;
    if (me.subscription && me.subscription.expires_at) {
      daysLeft = Math.max(0, Math.ceil((new Date(me.subscription.expires_at) - new Date()) / (1000 * 60 * 60 * 24)));
    }
    subscriptionBadge.classList.remove("hidden");
    const badgePlan = me.subscription ? planLabel(me.subscription.plan, me.subscription.plan) : "";
    subscriptionBadge.textContent = me.is_owner
      ? t("badge.owner")
      : isTrial
        ? t("badge.trial", { plan: badgePlan, d: daysLeft })
        : isTeamMember
          ? t("badge.team", { plan: badgePlan })
          : t("badge.active", { plan: badgePlan });
    subscriptionBadge.onclick = (me.is_owner || isTeamMember) ? null : cancelSubscription;
    subscriptionBadge.style.cursor = (me.is_owner || isTeamMember) ? "default" : "pointer";
    billingGate.classList.add("hidden");
    analysisArea.classList.remove("hidden");
    loadHistory();
    loadDatasets();
    loadTeamPanel(me.team_role);
  } else {
    subscriptionBadge.classList.add("hidden");
    analysisArea.classList.add("hidden");
    billingGate.classList.remove("hidden");
    loadPlans();
  }

  if (!me.is_owner && !me.email_verified) {
    verifyNudge.classList.remove("hidden");
    billingError.textContent = t("msg.unverified");
  } else {
    verifyNudge.classList.add("hidden");
  }
}

verifyNudge.addEventListener("click", async () => {
  const res = await fetch(`${API_BASE}/me`, { headers: authHeaders() });
  const me = await res.json();
  pendingVerifyEmail = me.email;
  otpEmailTarget.textContent = me.email;
  await fetch(`${API_BASE}/auth/resend-verification`, { method: "POST", headers: authHeaders() });
  authScreen.classList.remove("hidden");
  appScreen.classList.add("hidden");
  otpDigits.forEach((d) => (d.value = ""));
  otpError.textContent = "";
  showAuthStep("otp");
});

async function cancelSubscription() {
  if (!confirm(t("confirm.cancel_sub"))) return;
  await fetch(`${API_BASE}/billing/cancel`, { method: "POST", headers: authHeaders() });
  refreshAccountState();
}

async function loadPlans() {
  billingError.textContent = "";
  const [plansRes, trialsRes, meRes] = await Promise.all([
    fetch(`${API_BASE}/plans`),
    fetch(`${API_BASE}/trials`),
    fetch(`${API_BASE}/me`, { headers: authHeaders() }),
  ]);
  const plans = await plansRes.json();
  const trials = await trialsRes.json();
  const me = await meRes.json();
  const trialUsed = me.trial_used;

  plansGrid.innerHTML = "";
  for (const [planId, plan] of Object.entries(plans)) {
    const trial = trials[planId];
    const card = document.createElement("div");
    card.className = "plan-card";
    const perks = [t("plan.perk.analyses", { n: plan.analyze_per_day })];
    if (plan.max_seats > 1) perks.push(t("plan.perk.seats", { n: plan.max_seats }));
    if (plan.priority_support) perks.push(t("plan.perk.support"));

    let trialHtml = "";
    if (trial && !trialUsed) {
      trialHtml = `<button class="secondary-btn" data-trial-plan="${planId}" style="width:100%; margin-top:8px;">
        ${t("plan.trial", { d: trial.trial_days })}
      </button>`;
    } else if (trial && trial.convert_bonus_days > 0) {
      trialHtml = `<p class="muted small" style="margin-top:8px;">${t("plan.bonus", { d: trial.convert_bonus_days })}</p>`;
    }

    card.innerHTML = `
      <h3>${esc(planLabel(planId, plan.label))}</h3>
      <div class="price"><bdi>$${plan.price_usd}</bdi><span>${t("plan.per_month")}</span></div>
      <p class="muted small">${perks.join(" · ")}</p>
      <button class="primary-btn" data-plan="${planId}">${t("plan.choose")}</button>
      ${trialHtml}
    `;
    card.querySelector("[data-plan]").addEventListener("click", () => checkout(planId));
    const trialBtn = card.querySelector("[data-trial-plan]");
    if (trialBtn) trialBtn.addEventListener("click", () => startTrial(planId));
    plansGrid.appendChild(card);
  }
}

async function checkout(planId) {
  billingError.textContent = "";
  try {
    const res = await fetch(`${API_BASE}/billing/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ plan: planId }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.checkout_failed"));
    }
    const data = await res.json();
    // Send the user to Paymob's hosted payment page. After paying, Paymob
    // calls our webhook to activate the subscription; the user can come
    // back and refresh, or you can add a redirect-back URL in your Paymob
    // integration settings pointing back to this app.
    window.location.href = data.iframe_url;
  } catch (e) {
    billingError.textContent = e.message;
  }
}

async function startTrial(planId) {
  billingError.textContent = "";
  try {
    const res = await fetch(`${API_BASE}/billing/start-trial`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ plan: planId }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.trial_failed"));
    }
    await refreshAccountState();
  } catch (e) {
    billingError.textContent = e.message;
  }
}

// ── Team (Pro plan owners only) ───────────────────────────────────────
async function loadTeamPanel(teamRole) {
  if (teamRole !== "owner") {
    teamSection.classList.add("hidden");
    return;
  }
  teamSection.classList.remove("hidden");
  teamError.textContent = "";

  const res = await fetch(`${API_BASE}/team/members`, { headers: authHeaders() });
  if (!res.ok) {
    teamSection.classList.add("hidden");
    return;
  }
  const body = await res.json();
  teamSeatsLabel.textContent = t("team.seats_used", { used: body.used_seats, max: body.max_seats });

  teamMemberList.innerHTML = "";
  if (body.members.length === 0) {
    teamMemberList.innerHTML = `<p class="muted small">${t("team.empty")}</p>`;
  }
  for (const m of body.members) {
    const item = document.createElement("div");
    item.className = "team-member-item";
    item.innerHTML = `<span class="tm-email" dir="ltr">${esc(m.email)}</span><button class="tm-remove" data-id="${esc(m.id)}">${t("team.remove")}</button>`;
    item.querySelector(".tm-remove").addEventListener("click", () => removeTeamMember(m.id));
    teamMemberList.appendChild(item);
  }
}

teamInviteBtn.addEventListener("click", async () => {
  teamError.textContent = "";
  const email = teamInviteEmail.value.trim();
  if (!email) return;
  teamInviteBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/team/invite`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.invite_failed"));
    }
    teamInviteEmail.value = "";
    await refreshAccountState();
  } catch (e) {
    teamError.textContent = e.message;
  } finally {
    teamInviteBtn.disabled = false;
  }
});

async function removeTeamMember(id) {
  if (!confirm(t("confirm.remove_member"))) return;
  await fetch(`${API_BASE}/team/members/${id}`, { method: "DELETE", headers: authHeaders() });
  refreshAccountState();
}

// ── Datasets ────────────────────────────────────────────────────────────
let datasetsCache = [];

function showDatasetForm(which) {
  uploadForm.classList.toggle("hidden", which !== "upload");
  connectForm.classList.toggle("hidden", which !== "connect");
  uploadError.textContent = "";
  connectError.textContent = "";
}
showUploadBtn.addEventListener("click", () => showDatasetForm("upload"));
showConnectBtn.addEventListener("click", () => showDatasetForm("connect"));
uploadCancelBtn.addEventListener("click", () => showDatasetForm(null));
connectCancelBtn.addEventListener("click", () => showDatasetForm(null));

async function loadDatasets() {
  const res = await fetch(`${API_BASE}/datasets`, { headers: authHeaders() });
  if (!res.ok) return;
  datasetsCache = await res.json();

  datasetList.innerHTML = "";
  if (datasetsCache.length === 0) {
    datasetList.innerHTML = `<p class="muted">${t("ds.empty")}</p>`;
  }
  for (const d of datasetsCache) {
    const item = document.createElement("div");
    item.className = "dataset-item";
    const meta = d.source_type === "file"
      ? t("ds.meta.file", { rows: d.row_count, cols: d.columns.length })
      : `${d.db_type} · ${d.host}/${d.database}`;
    item.innerHTML = `
      <div><div class="ds-name">${esc(d.name)}</div><div class="ds-meta">${esc(meta)}</div></div>
      <button class="ds-remove" data-id="${esc(d.id)}">${t("ds.remove")}</button>
    `;
    item.querySelector(".ds-remove").addEventListener("click", () => removeDataset(d.id));
    datasetList.appendChild(item);
  }

  const previouslySelected = datasetPicker.value;
  datasetPicker.innerHTML = "";
  if (datasetsCache.length === 0) {
    datasetPicker.innerHTML = `<option value="">${t("ds.picker.empty")}</option>`;
  } else {
    for (const d of datasetsCache) {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = d.name;
      datasetPicker.appendChild(opt);
    }
    if (datasetsCache.some((d) => d.id === previouslySelected)) {
      datasetPicker.value = previouslySelected;
    }
  }
}

async function removeDataset(id) {
  if (!confirm(t("confirm.remove_dataset"))) return;
  await fetch(`${API_BASE}/datasets/${id}`, { method: "DELETE", headers: authHeaders() });
  loadDatasets();
}

uploadSubmitBtn.addEventListener("click", async () => {
  uploadError.textContent = "";
  const name = uploadName.value.trim();
  const file = uploadFile.files[0];
  if (!name || !file) {
    uploadError.textContent = t("msg.upload_fields");
    return;
  }
  uploadSubmitBtn.disabled = true;
  try {
    const formData = new FormData();
    formData.append("name", name);
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/datasets/upload`, {
      method: "POST",
      headers: authHeaders(), // no Content-Type — browser sets multipart boundary
      body: formData,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.upload_failed"));
    }
    uploadName.value = "";
    uploadFile.value = "";
    showDatasetForm(null);
    loadDatasets();
  } catch (e) {
    uploadError.textContent = e.message;
  } finally {
    uploadSubmitBtn.disabled = false;
  }
});

connectSubmitBtn.addEventListener("click", async () => {
  connectError.textContent = "";
  const payload = {
    name: connectName.value.trim(),
    db_type: connectType.value,
    host: connectHost.value.trim(),
    port: parseInt(connectPort.value, 10),
    database: connectDb.value.trim(),
    user: connectUser.value.trim(),
    password: connectPassword.value,
  };
  if (!payload.name || !payload.host || !payload.database || !payload.user || !payload.port) {
    connectError.textContent = t("msg.connect_fields");
    return;
  }
  connectSubmitBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/datasets/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.connect_failed"));
    }
    [connectName, connectHost, connectPort, connectDb, connectUser, connectPassword].forEach((el) => (el.value = ""));
    showDatasetForm(null);
    loadDatasets();
  } catch (e) {
    connectError.textContent = e.message;
  } finally {
    connectSubmitBtn.disabled = false;
  }
});

// ── Analysis ────────────────────────────────────────────────────────────
function renderSection(title, value, key) {
  const section = document.createElement("section");
  const h3 = document.createElement("h3");
  h3.textContent = title;
  const pre = document.createElement("pre");
  pre.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  // SQL is always left-to-right; report prose picks its direction from its own text (Arabic or English).
  pre.setAttribute("dir", key === "sql_query" ? "ltr" : "auto");
  section.appendChild(h3);
  section.appendChild(pre);
  return section;
}

let lastResult = null; // kept so the section titles can be re-rendered when the language is toggled

function renderResults(result) {
  lastResult = result;
  resultsContent.innerHTML = "";
  const order = [
    "business_context", "sql_query", "quality_interpretation", "statistics_interpretation",
    "correlation_interpretation", "trend_interpretation", "outlier_interpretation",
    "more_analysis_interpretation", "eda", "root_cause", "insights", "recommendations",
  ];
  for (const key of order) {
    if (result[key] !== undefined) {
      resultsContent.appendChild(renderSection(t("res." + key), result[key], key));
    }
  }
  resultsSection.classList.remove("hidden");
}

function updateQuestionPlaceholder() {
  questionInput.placeholder = followUpFromReportId ? t("ph.question.followup") : t("ph.question");
}

function clearFollowUp() {
  followUpFromReportId = null;
  followupChip.classList.add("hidden");
  updateQuestionPlaceholder();
}
followupClear.addEventListener("click", clearFollowUp);

async function ask() {
  askError.textContent = "";
  const question = questionInput.value.trim();
  const datasetId = datasetPicker.value;
  if (!datasetId) {
    askError.textContent = t("msg.need_dataset");
    return;
  }
  if (!question) {
    askError.textContent = t("msg.need_question");
    return;
  }

  resultsSection.classList.add("hidden");
  loading.classList.remove("hidden");
  askBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ question, dataset_id: datasetId, prior_report_id: followUpFromReportId, language: I18N.lang() }),
    });
    if (res.status === 401) {
      logout();
      throw new Error(t("msg.session_expired"));
    }
    if (res.status === 402) {
      throw new Error(t("msg.sub_inactive"));
    }
    if (res.status === 429) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.limit_reached"));
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(apiError(body, "msg.analysis_failed"));
    }
    const data = await res.json();
    currentReportId = data.report_id;
    clearFollowUp();
    renderResults(data);
    loadHistory();
  } catch (e) {
    askError.textContent = e.message;
  } finally {
    loading.classList.add("hidden");
    askBtn.disabled = false;
  }
}

function improveCurrent() {
  if (!currentReportId) return;
  followUpFromReportId = currentReportId;
  followupChip.classList.remove("hidden");
  questionInput.value = "";
  updateQuestionPlaceholder();
  questionInput.focus();
  window.scrollTo({ top: questionInput.offsetTop - 100, behavior: "smooth" });
}

async function downloadPdf(reportId) {
  const id = reportId || currentReportId;
  if (!id) return;
  const res = await fetch(`${API_BASE}/report/${id}/pdf`, { headers: authHeaders() });
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "AI_Analyst_Report.pdf";
  a.click();
  URL.revokeObjectURL(url);
}

async function loadHistory() {
  const res = await fetch(`${API_BASE}/reports`, { headers: authHeaders() });
  if (!res.ok) return;
  const body = await res.json();
  const reports = body.items || [];

  historyList.innerHTML = "";
  if (reports.length === 0) {
    historyList.innerHTML = `<p class="muted">${t("history.empty")}</p>`;
    return;
  }
  for (const r of reports) {
    const item = document.createElement("div");
    item.className = "history-item";
    const date = I18N.formatDate(r.created_at);
    item.innerHTML = `<span class="q" dir="auto">${esc(r.question)}</span><span class="date">${esc(date)}</span>`;
    item.addEventListener("click", () => downloadPdf(r.id));
    historyList.appendChild(item);
  }
}

askBtn.addEventListener("click", ask);
downloadPdfBtn.addEventListener("click", () => downloadPdf());
improveBtn.addEventListener("click", improveCurrent);

// ── Language switch ─────────────────────────────────────────────────────
// Static text is re-translated by i18n.js itself; this re-renders everything
// that app.js builds dynamically (badge, plans, datasets, history, results).
window.addEventListener("langchange", () => {
  document.querySelectorAll(".error").forEach((el) => (el.textContent = ""));
  updateQuestionPlaceholder();
  if (lastResult) renderResults(lastResult);
  if (!appScreen.classList.contains("hidden")) refreshAccountState();
});

// ── Boot ────────────────────────────────────────────────────────────────
updateQuestionPlaceholder();
if (getToken()) {
  showApp();
} else {
  showAuth();
}