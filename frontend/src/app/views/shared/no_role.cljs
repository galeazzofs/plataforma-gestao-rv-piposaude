(ns app.views.shared.no-role
  (:require [re-frame.core :as rf]
            [app.ds.tokens :as t]
            [app.ds.layout :as layout]
            [app.ds.buttons :as btn]))

;; Sem perfil — tela mostrada após o login quando o usuário ainda não foi
;; promovido a um role. Reúsa a estética do login (painel night à esquerda).

(defn no-role-page []
  [:div.login-frame
   ;; Brand panel
   [:div {:style {:position "relative" :padding "64px"
                  :display "flex" :flex-direction "column" :justify-content "space-between"
                  :background t/color-night :color t/color-white :overflow "hidden"}}
    [:div {:class "dot-grid"}]
    [:div {:style {:position "absolute" :inset 0
                   :background (str "radial-gradient(circle at 30% 70%," t/color-cyan " 0%,transparent 60%)")
                   :opacity 0.18}}]
    [:div {:style {:position "relative" :z-index 1 :display "flex" :gap "14px" :align-items "center"}}
     [:div {:style {:width "42px" :height "42px" :border-radius "12px"
                    :background t/color-white :overflow "hidden"
                    :display "flex" :align-items "center" :justify-content "center"}}
      [:img {:src "/img/pipo-mark-light.png" :alt "Pipo Saúde"
             :style {:width "42px" :height "42px" :display "block"}}]]
     [:div
      [:strong {:style {:font-family t/font-heading :font-size "17px" :font-weight "600"}}
       "Pipo Saúde"]
      [:div {:style {:font-family t/font-mono :font-size "11px"
                     :color "rgba(255,255,255,0.6)" :letter-spacing "0.04em"}}
       "plataforma · rv"]]]
    [:div {:style {:position "relative" :z-index 1 :max-width "420px"}}
     [:div {:style {:font-family t/font-mono :font-size "11px" :color t/color-cyan
                    :text-transform "uppercase" :letter-spacing "0.08em"
                    :margin-bottom "14px"}}
      "acesso pendente"]
     [:h1 {:style {:font-family t/font-display :font-size "52px" :font-weight "600"
                   :line-height "1.05" :color t/color-white
                   :letter-spacing "-0.015em" :margin 0}}
      "Quase lá."]
     [:p {:style {:font-size "15px" :color "rgba(255,255,255,0.7)"
                  :margin-top "18px" :line-height "1.5"}}
      "Sua conta está criada, mas ainda não tem um perfil de acesso. Avise o RevOps que tudo bem, a gente libera em minutos."]]
    [:div {:style {:position "relative" :z-index 1
                   :font-family t/font-mono :font-size "11px"
                   :color "rgba(255,255,255,0.5)"}}
     "© 2026 Pipo Saúde"]]

   ;; Action panel
   [:div {:style {:background t/bg-card :padding "64px 72px"
                  :display "flex" :flex-direction "column" :justify-content "center" :gap "20px"}}
    [:div
     [:div {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary
                    :text-transform "uppercase" :letter-spacing "0.06em"
                    :margin-bottom "8px"}}
      "aguardando atribuição"]
     [:h2 {:style {:font-family t/font-display :font-weight "600" :font-size "30px"
                   :color t/text-primary :margin 0 :letter-spacing "-0.005em"}}
      "Sem perfil ainda"]
     [:p {:style {:font-size "13px" :color t/text-tertiary :margin-top "8px" :line-height "1.6"}}
      "Solicite ao administrador da plataforma para configurar seu acesso. Assim que ele atribuir um role (EV, CN, Líder de Vendas, Finance ou RevOps), você terá acesso ao painel correspondente."]]

    [:div.callout
     [layout/icon "info" {:width 20 :height 20}]
     [:div
      [:strong "Quer adiantar?"]
      [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
       "Mande seu e-mail para o RevOps lá no Slack ou peça à liderança do seu time."]]]

    [btn/button {:variant :secondary :size :lg :full-width true
                 :on-click #(rf/dispatch [:auth/logout])}
     "Sair e tentar com outra conta"]]])
