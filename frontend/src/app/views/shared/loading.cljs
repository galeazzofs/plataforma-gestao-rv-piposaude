(ns app.views.shared.loading
  (:require [app.ds.tokens :as t]))

(defn page []
  [:div {:style {:min-height      "100vh"
                 :display         "flex"
                 :align-items     "center"
                 :justify-content "center"
                 :background      t/bg-main}}
   [:div {:style {:display        "flex"
                  :flex-direction "column"
                  :align-items    "center"
                  :gap            "16px"}}
    [:div {:style {:width         "40px"
                   :height        "40px"
                   :border        (str "3px solid " t/border-default)
                   :border-top    (str "3px solid " t/color-primary)
                   :border-radius (:full t/border-radius)
                   :animation     "spin 0.8s linear infinite"}}]
    [:p {:style {:color     t/text-secondary
                 :font-size (:sm t/font-sizes)
                 :margin    "0"}}
     "Carregando..."]]
   [:style "
     @keyframes spin {
       from { transform: rotate(0deg); }
       to   { transform: rotate(360deg); }
     }"]])
