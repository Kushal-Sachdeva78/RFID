// Firebase initialization for the RFID dashboard.
// Uses ESM imports directly from Google's CDN so no build tooling is required.
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app.js";
import { getAnalytics, isSupported } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-analytics.js";
import {
  getFirestore,
  collection,
  addDoc,
  serverTimestamp,
} from "https://www.gstatic.com/firebasejs/10.7.1/firebase-firestore.js";

// Firebase configuration provided by the project owner.
const firebaseConfig = {
  apiKey: "AIzaSyCu0eajMj6wsOZN6YAa5a4y1nJqbFGRQt4",
  authDomain: "rfid-a9353.firebaseapp.com",
  projectId: "rfid-a9353",
  storageBucket: "rfid-a9353.firebasestorage.app",
  messagingSenderId: "1032115456459",
  appId: "1:1032115456459:web:f969ac442b97e9f71bce4e",
  measurementId: "G-CPEZ5NSW66",
};

const firebaseApp = initializeApp(firebaseConfig);

const analyticsPromise = isSupported()
  .then((supported) => (supported ? getAnalytics(firebaseApp) : null))
  .catch(() => null);

const db = getFirestore(firebaseApp);

export { firebaseApp, analyticsPromise, db, collection, addDoc, serverTimestamp };
