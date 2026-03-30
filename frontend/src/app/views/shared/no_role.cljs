(ns app.views.shared.no-role
  (:require [re-frame.core :as rf]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

(defn no-role-page []
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
    [:h2 {:style {:font-size     (:2xl t/font-sizes)
                  :font-weight   (:bold t/font-weights)
                  :color         t/text-primary
                  :margin-bottom "8px"
                  :margin-top    "0"}}
     "Aguardando atribuicao de role"]
    [:p {:style {:color         t/text-secondary
                 :margin-bottom "24px"
                 :font-size     (:sm t/font-sizes)
                 :margin-top    "0"}}
     "Sua conta foi criada, mas ainda nao tem um perfil de acesso atribuido. "
     "Solicite ao administrador da plataforma para configurar seu acesso."]
    [btn/button {:variant  :secondary
                 :on-click #(rf/dispatch [:auth/logout])}
     "Sair"]]])
