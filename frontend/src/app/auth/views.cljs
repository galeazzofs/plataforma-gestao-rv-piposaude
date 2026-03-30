(ns app.auth.views
  (:require [re-frame.core :as rf]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

(defn login-page []
  (let [loading? @(rf/subscribe [:auth/loading?])
        error    @(rf/subscribe [:auth/error])]
    [:div {:style {:min-height       "100vh"
                   :display          "flex"
                   :align-items      "center"
                   :justify-content  "center"
                   :background       t/bg-main}}
     [:div {:style {:background    t/bg-card
                    :padding       "48px"
                    :border-radius (:xl t/border-radius)
                    :box-shadow    (:lg t/shadows)
                    :text-align    "center"
                    :width         "400px"}}
      ;; Heading
      [:h1 {:style {:font-size     (:3xl t/font-sizes)
                    :font-weight   (:bold t/font-weights)
                    :color         t/color-primary
                    :margin-bottom "8px"
                    :margin-top    "0"}}
       "Comissoes"]
      ;; Subtitle
      [:p {:style {:color         t/text-secondary
                   :margin-bottom "32px"
                   :font-size     (:sm t/font-sizes)
                   :margin-top    "0"}}
       "Plataforma de gestao de comissoes — Pipo Saude"]
      ;; Error card
      (when error
        [:div {:style {:background    t/error-light
                       :color         t/error-dark
                       :padding       "12px"
                       :border-radius (:md t/border-radius)
                       :margin-bottom "16px"
                       :font-size     (:sm t/font-sizes)}}
         error])
      ;; Google SSO button
      [btn/button {:variant    :primary
                   :size       :lg
                   :full-width true
                   :loading    loading?
                   :on-click   #(js/console.log "Google SSO — will integrate with gapi")}
       "Entrar com Google"]]]))
