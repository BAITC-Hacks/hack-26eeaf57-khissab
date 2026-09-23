import React from "react";
import { createRoot } from "react-dom/client";
import "./index.css";

function App() {
  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-semibold">Career Quest</h1>
      <p className="mt-3 max-w-2xl text-gray-600">
        Scaffold ready. Employee and HR views will be implemented after the
        loader, recommendation engine, explanation layer, and API are verified.
      </p>
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
