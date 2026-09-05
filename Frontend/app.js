const API_BASE = ""; // same-origin; change if the API is hosted elsewhere

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
      throw new Error(body.detail || "Login failed.");
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
    signupError.textContent = "Password must be at least 8 characters.";
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
      throw new Error(body.detail || "Signup failed.");
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
  forgotNote.textContent = "If that email has an account, a reset link is on its way.";
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
    otpError.textContent = "Enter all 6 digits.";
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
      throw new Error(body.detail || "That code didn't work.");
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
  otpError.textContent = res.ok ? "Sent — check your inbox." : "Couldn't resend right now.";
});

// ── Google / Apple sign-in (via Firebase, see firebase-init.js) ───────
async function socialSignIn(getIdToken, button) {
  loginError.textContent = "";
  button.disabled = true;
  try {
    if (!window.firebaseAuthReady) {
      throw new Error("Sign-in is still loading — try again in a second.");
    }
    const idToken = await getIdToken();
    const res = await fetch(`${API_BASE}/auth/firebase`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Sign-in failed.");
    }
    const data = await res.json();
    setToken(data.access_token);
    showApp();
  } catch (e) {
    loginError.textContent = e.message || "Sign-in was cancelled or failed.";
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
    subscriptionBadge.textContent = me.is_owner
      ? "Owner account"
      : isTrial
        ? `${me.subscription.plan} trial — ${daysLeft}d left (cancel)`
        : isTeamMember
          ? `${me.subscription.plan} — team seat`
          : `${me.subscription.plan} — active (cancel)`;
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
    billingError.textContent = "Your email isn't verified yet — check your inbox for a code.";
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
  if (!confirm("Cancel your subscription? Access ends immediately.")) return;
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
    const perks = [`${plan.analyze_per_day} analyses/day`];
    if (plan.max_seats > 1) perks.push(`${plan.max_seats} team seats`);
    if (plan.priority_support) perks.push("priority support");

    let trialHtml = "";
    if (trial && !trialUsed) {
      trialHtml = `<button class="secondary-btn" data-trial-plan="${planId}" style="width:100%; margin-top:8px;">
        ${trial.trial_days}-day free trial — no card needed
      </button>`;
    } else if (trial && trial.convert_bonus_days > 0) {
      trialHtml = `<p class="muted small" style="margin-top:8px;">+${trial.convert_bonus_days} bonus days if you tried this plan's trial first</p>`;
    }

    card.innerHTML = `
      <h3>${plan.label}</h3>
      <div class="price">$${plan.price_usd}<span>/mo</span></div>
      <p class="muted small">${perks.join(" · ")}</p>
      <button class="primary-btn" data-plan="${planId}">Choose</button>
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
      throw new Error(body.detail || "Could not start checkout.");
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
      throw new Error(body.detail || "Could not start your trial.");
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
  teamSeatsLabel.textContent = `${body.used_seats} / ${body.max_seats} seats used`;

  teamMemberList.innerHTML = "";
  if (body.members.length === 0) {
    teamMemberList.innerHTML = '<p class="muted small">Just you so far — invite a teammate below.</p>';
  }
  for (const m of body.members) {
    const item = document.createElement("div");
    item.className = "team-member-item";
    item.innerHTML = `<span class="tm-email">${m.email}</span><button class="tm-remove" data-id="${m.id}">Remove</button>`;
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
      throw new Error(body.detail || "Could not add that person.");
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
  if (!confirm("Remove this teammate from your plan?")) return;
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
    datasetList.innerHTML = '<p class="muted">No datasets yet — upload a file or connect a database to get started.</p>';
  }
  for (const d of datasetsCache) {
    const item = document.createElement("div");
    item.className = "dataset-item";
    const meta = d.source_type === "file"
      ? `${d.row_count} rows · ${d.columns.length} columns`
      : `${d.db_type} · ${d.host}/${d.database}`;
    item.innerHTML = `
      <div><div class="ds-name">${d.name}</div><div class="ds-meta">${meta}</div></div>
      <button class="ds-remove" data-id="${d.id}">Remove</button>
    `;
    item.querySelector(".ds-remove").addEventListener("click", () => removeDataset(d.id));
    datasetList.appendChild(item);
  }

  const previouslySelected = datasetPicker.value;
  datasetPicker.innerHTML = "";
  if (datasetsCache.length === 0) {
    datasetPicker.innerHTML = '<option value="">No datasets yet — add one above</option>';
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
  if (!confirm("Remove this dataset? This can't be undone.")) return;
  await fetch(`${API_BASE}/datasets/${id}`, { method: "DELETE", headers: authHeaders() });
  loadDatasets();
}

uploadSubmitBtn.addEventListener("click", async () => {
  uploadError.textContent = "";
  const name = uploadName.value.trim();
  const file = uploadFile.files[0];
  if (!name || !file) {
    uploadError.textContent = "Give it a name and pick a file.";
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
      throw new Error(body.detail || "Upload failed.");
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
    connectError.textContent = "Fill in all fields.";
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
      throw new Error(body.detail || "Could not connect.");
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
function renderSection(title, value) {
  const section = document.createElement("section");
  const h3 = document.createElement("h3");
  h3.textContent = title;
  const pre = document.createElement("pre");
  pre.textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  section.appendChild(h3);
  section.appendChild(pre);
  return section;
}

function renderResults(result) {
  resultsContent.innerHTML = "";
  const order = [
    ["Business Context", "business_context"],
    ["SQL Query", "sql_query"],
    ["Data Quality", "quality_interpretation"],
    ["Statistics", "statistics_interpretation"],
    ["Correlations", "correlation_interpretation"],
    ["Trend", "trend_interpretation"],
    ["Outliers", "outlier_interpretation"],
    ["More Analysis", "more_analysis_interpretation"],
    ["EDA", "eda"],
    ["Root Cause", "root_cause"],
    ["Insights", "insights"],
    ["Recommendations", "recommendations"],
  ];
  for (const [title, key] of order) {
    if (result[key] !== undefined) {
      resultsContent.appendChild(renderSection(title, result[key]));
    }
  }
  resultsSection.classList.remove("hidden");
}

function clearFollowUp() {
  followUpFromReportId = null;
  followupChip.classList.add("hidden");
}
followupClear.addEventListener("click", clearFollowUp);

async function ask() {
  askError.textContent = "";
  const question = questionInput.value.trim();
  const datasetId = datasetPicker.value;
  if (!datasetId) {
    askError.textContent = "Add a dataset first (upload a file or connect a database above).";
    return;
  }
  if (!question) {
    askError.textContent = "Type a question first.";
    return;
  }

  resultsSection.classList.add("hidden");
  loading.classList.remove("hidden");
  askBtn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ question, dataset_id: datasetId, prior_report_id: followUpFromReportId }),
    });
    if (res.status === 401) {
      logout();
      throw new Error("Session expired — please log in again.");
    }
    if (res.status === 402) {
      throw new Error("Your subscription is no longer active. Please renew.");
    }
    if (res.status === 429) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Daily analysis limit reached.");
    }
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Analysis failed.");
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
  questionInput.placeholder = "What should the AI dig into or fix from that last report?";
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
    historyList.innerHTML = '<p class="muted">No analyses yet — ask your first question above.</p>';
    return;
  }
  for (const r of reports) {
    const item = document.createElement("div");
    item.className = "history-item";
    const date = new Date(r.created_at).toLocaleString();
    item.innerHTML = `<span class="q">${r.question}</span><span class="date">${date}</span>`;
    item.addEventListener("click", () => downloadPdf(r.id));
    historyList.appendChild(item);
  }
}

askBtn.addEventListener("click", ask);
downloadPdfBtn.addEventListener("click", () => downloadPdf());
improveBtn.addEventListener("click", improveCurrent);

// ── Boot ────────────────────────────────────────────────────────────────
if (getToken()) {
  showApp();
} else {
  showAuth();
}