(ns app.config)

(def api-base-url "/api/v1")

(def google-client-id
  (or (.-GOOGLE_CLIENT_ID js/window) ""))

(def app-name "Comissões Pipo")
