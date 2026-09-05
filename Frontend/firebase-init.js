// ── Firebase client config ───────────────────────────────────────────────
// Paste the config object from: Firebase Console → Project Settings →
// General → Your apps → Web app → SDK setup and configuration.
// This is the *public* web config (apiKey here is safe to expose — it's
// not a secret, it just identifies your Firebase project to Google's
// servers). Do NOT put your service-account JSON here; that stays on the
// backend only (see AI_Analyst_App/config.py).
const firebaseConfig = {
  apiKey: "AIzaSyCCMLgX-7s-YLezNY3m9s4cMgTk3Ff7MG8",
  authDomain: "ai-analyst-fc904.firebaseapp.com",
  projectId: "ai-analyst-fc904",
  appId: "1:327900770907:web:5d305ad3d8e57324bb857e",
};

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  OAuthProvider,
  signInWithPopup,
} from "https://www.gstatic.com/firebasejs/10.13.0/firebase-auth.js";

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

async function signInWithGoogle() {
  const provider = new GoogleAuthProvider();
  const result = await signInWithPopup(auth, provider);
  return result.user.getIdToken();
}

async function signInWithApple() {
  // Requires "Apple" enabled as a sign-in provider in Firebase Console →
  // Authentication → Sign-in method (you said you've already flipped this on).
  const provider = new OAuthProvider("apple.com");
  provider.addScope("email");
  provider.addScope("name");
  const result = await signInWithPopup(auth, provider);
  return result.user.getIdToken();
}

// Exposed to app.js (a plain, non-module script) via window, since mixing
// module-scoped Firebase imports with the rest of the app's plain script
// is simplest this way and avoids a build step entirely.
window.firebaseAuthReady = true;
window.signInWithGoogle = signInWithGoogle;
window.signInWithApple = signInWithApple;

