(ns app.config)

(def api-base-url
  ;; Dev (shadow-cljs watch → goog.DEBUG=true) serves the SPA on :8080 while
  ;; Flask serves the API on :5000 — a different origin — so dev needs the
  ;; absolute backend URL (CORS allows :8080). Release builds (goog.DEBUG=false)
  ;; are served same-origin behind nginx, where the relative path is correct.
  (if ^boolean goog.DEBUG
    "http://localhost:5000/api/v1"
    "/api/v1"))

(def google-client-id
  (or (.-GOOGLE_CLIENT_ID js/window) ""))

(def app-name "Comissões Pipo")
