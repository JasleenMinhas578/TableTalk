import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "sonner";

import "@fontsource/fredoka/500.css";
import "@fontsource/fredoka/600.css";
import "@fontsource/figtree/400.css";
import "@fontsource/figtree/500.css";
import "@fontsource/figtree/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@xyflow/react/dist/style.css";
import "./styles.css";

import App from "./App.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
    <Toaster position="bottom-right" richColors closeButton />
  </React.StrictMode>
);
