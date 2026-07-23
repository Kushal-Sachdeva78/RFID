// Copy this file to firebase.config.js and fill in your Firebase project values.
// firebase.config.js is gitignored so a specific project is never committed.
//
// A Firebase web apiKey is not a secret (it ships to every browser), but keeping
// it out of the repository avoids tying this public code to one live project.
// The real protection is the Firestore security rules (see GETTING_STARTED.md).
export const firebaseConfig = {
  apiKey: "YOUR_API_KEY",
  authDomain: "YOUR_PROJECT.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT.appspot.com",
  messagingSenderId: "YOUR_SENDER_ID",
  appId: "YOUR_APP_ID",
  measurementId: "YOUR_MEASUREMENT_ID",
};
