(ns app.views.shared.loading
  (:require [app.ds.tokens :as t]))

;; Loading screen — Pipo styling: minimal centered spinner + lowercase mono label.

(defn page []
  [:div {:style {:min-height "100vh"
                 :display "flex" :align-items "center" :justify-content "center"
                 :background t/bg-main}}
   [:div {:style {:display "flex" :flex-direction "column"
                  :align-items "center" :gap "16px"}}
    [:div {:style {:width "32px" :height "32px"
                   :border (str "2px solid " t/border-default)
                   :border-top (str "2px solid " t/text-primary)
                   :border-radius "9999px"
                   :animation "spin 0.8s linear infinite"}}]
    [:p {:style {:font-family t/font-mono :font-size "12px"
                 :color t/text-tertiary :margin 0
                 :text-transform "lowercase" :letter-spacing "0.06em"}}
     "carregando…"]]])
