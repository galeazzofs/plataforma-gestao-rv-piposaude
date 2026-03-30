(ns app.config)

(def api-base-url
  (if ^boolean goog.DEBUG
    "http://localhost:5000/api/v1"
    "/api/v1"))

(def google-client-id
  (or (.-GOOGLE_CLIENT_ID js/window) ""))

(def app-name "Comissões Pipo")
