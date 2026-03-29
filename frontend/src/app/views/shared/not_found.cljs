(ns app.views.shared.not-found
  (:require [re-frame.core :as rf]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

(defn page []
  [:div {:style {:min-height      "100vh"
                 :display         "flex"
                 :align-items     "center"
                 :justify-content "center"
                 :background      t/bg-main}}
   [:div {:style {:background    t/bg-card
                  :padding       "48px"
                  :border-radius (:xl t/border-radius)
                  :box-shadow    (:lg t/shadows)
                  :text-align    "center"
                  :max-width     "480px"}}
    [:h1 {:style {:font-size     "72px"
                  :font-weight   (:bold t/font-weights)
                  :color         t/text-disabled
                  :margin        "0 0 8px"}}
     "404"]
    [:h2 {:style {:font-size     (:xl t/font-sizes)
                  :font-weight   (:semibold t/font-weights)
                  :color         t/text-primary
                  :margin-bottom "8px"
                  :margin-top    "0"}}
     "Pagina nao encontrada"]
    [:p {:style {:color         t/text-secondary
                 :margin-bottom "24px"
                 :font-size     (:sm t/font-sizes)
                 :margin-top    "0"}}
     "A pagina que voce esta procurando nao existe ou foi movida."]
    [btn/button {:variant  :primary
                 :on-click #(rf/dispatch [:navigate :login])}
     "Voltar para o inicio"]]])
