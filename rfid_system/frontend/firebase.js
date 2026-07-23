// Firebase initialization for the RFID dashboard.
// Uses ESM imports directly from Google's CDN so no build tooling is required.
//
// The Firebase project config is loaded from firebase.config.js, which is NOT
// committed. Copy firebase.config.example.js to firebase.config.js and fill in
// your project values. When that file is absent (as in a fresh clone), Firestore
// mirroring is simply disabled and the rest of the dashboard works normally.
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { getAnalytics, isSupported } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-analytics.js";
import {
  getFirestore,
  collection,
  addDoc,
  serverTimestamp,
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";

let firebaseConfig = null;
try {
  const module = await import("./firebase.config.js");
  firebaseConfig = module.firebaseConfig;
} catch (error) {
  console.info(
    "firebase.config.js not found; Firestore mirroring is disabled. " +
      "Copy firebase.config.example.js to firebase.config.js to enable it."
  );
}

let db = null;
let analyticsPromise = Promise.resolve(null);

if (firebaseConfig && firebaseConfig.apiKey && !firebaseConfig.apiKey.startsWith("YOUR_")) {
  const firebaseApp = initializeApp(firebaseConfig);
  analyticsPromise = isSupported()
    .then((supported) => (supported ? getAnalytics(firebaseApp) : null))
    .catch(() => null);
  db = getFirestore(firebaseApp);
}

export { analyticsPromise, db, collection, addDoc, serverTimestamp };
