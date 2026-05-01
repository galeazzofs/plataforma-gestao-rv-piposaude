(ns app.views.shared.not-found
  (:require [re-frame.core :as rf]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]
            [app.ds.layout :as layout]))

;; 404 — Pipo styling: serif hero number, lowercase mono kicker, ghost CTAs.

(defn page []
  [:div {:style {:min-height "100vh"
                 :display "flex" :align-items "center" :justify-content "center"
                 :padding "32px"
                 :background t/bg-main :font-family t/font-body}}
   [:div {:style {:background t/bg-card
                  :border (str "1px solid " t/border-default)
                  :padding "56px 64px"
                  :border-radius (:lg t/border-radius)
                  :box-shadow (:md t/shadows)
                  :text-align "center"
                  :max-width "520px" :width "100%"
                  :display "flex" :flex-direction "column" :gap "16px"
                  :align-items "center"}}
    [:div {:style {:font-family t/font-mono :font-size "11px"
                   :color t/text-tertiary :text-transform "uppercase"
                   :letter-spacing "0.08em"}}
     "404 · página perdida"]
    [:h1 {:style {:font-family t/font-display :font-size "96px" :font-weight "400"
                  :color t/text-primary :margin 0 :line-height "1"
                  :letter-spacing "-0.015em"}}
     "Ops."]
    [:p {:style {:color t/text-tertiary :font-size "14px" :line-height "1.6"
                 :max-width "360px" :margin 0}}
     "A página que você procura não existe ou foi movida. Verifique a URL ou volte para o painel."]
    [:div {:style {:display "flex" :gap "10px" :justify-content "center" :margin-top "8px"}}
     [btn/button {:variant :secondary
                  :on-click #(.back js/history)}
      "← Voltar"]
     [btn/button {:variant :primary
                  :on-click #(rf/dispatch [:navigate :revops/dashboard])}
      [layout/icon "dashboard" {:width 14 :height 14}] "Ir para dashboard"]]]])
