(ns app.auth.views
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

;; ============================================
;; Login page — split-pane night/cyan brand panel + form panel,
;; mirroring the .login-frame design from the Pipo handoff.
;; ============================================

(defn role-badge-style [role]
  (case role
    "ADMIN"    {:background t/color-primary :color t/color-white}
    "FINANCE"  {:background t/blue-700      :color t/color-white}
    "GERENTE"  {:background t/purple-700    :color t/color-white}
    "EV"       {:background t/success-default :color t/color-white}
    "CN"       {:background t/beige-500    :color t/text-secondary}
    {:background t/bg-subtle :color t/text-secondary}))

(defn- fetch-dev-users! [users-atom loading-atom]
  (-> (js/fetch "/api/v1/auth/dev-users")
      (.then (fn [resp] (.json resp)))
      (.then (fn [json]
               (let [items (aget json "data")]
                 (reset! users-atom (js->clj items :keywordize-keys true))
                 (reset! loading-atom false))))
      (.catch (fn [err]
                (js/console.error "dev-users fetch error:" err)
                (reset! loading-atom false)))))

(defn dev-login-picker
  "Dev-only: shows a list of seeded users to login as."
  []
  (let [users    (r/atom nil)
        loading? (r/atom true)]
    (r/create-class
     {:component-did-mount
      (fn [_this]
        (fetch-dev-users! users loading?))

      :reagent-render
      (fn []
        [:div
         [:div {:style {:display "flex" :align-items "center" :gap "12px" :margin "8px 0 14px"}}
          [:div {:style {:flex "1" :height "1px" :background t/border-default}}]
          [:span {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary
                          :text-transform "uppercase" :letter-spacing "0.08em"
                          :white-space "nowrap"}}
           "Acesso de Desenvolvimento"]
          [:div {:style {:flex "1" :height "1px" :background t/border-default}}]]

         (if @loading?
           [:div {:style {:text-align "center" :padding "16px" :color t/text-disabled
                          :font-family t/font-mono :font-size "12px"}}
            "Carregando usuários..."]
           [:div {:style {:display "flex" :flex-direction "column" :gap "8px"
                          :max-height "260px" :overflow-y "auto"}}
            (for [user @users]
              ^{:key (:email user)}
              [:div {:style {:display "flex"
                             :justify-content "space-between"
                             :align-items "center"
                             :padding "10px 12px"
                             :border-radius (:sm t/border-radius)
                             :border (str "1px solid " t/border-default)
                             :cursor "pointer"
                             :transition (str "all " t/transition-fast)
                             :background t/bg-card}
                     :on-click #(rf/dispatch [:auth/dev-login (:email user)])}
               [:div
                [:div {:style {:font-family t/font-ui :font-size "13px"
                               :font-weight (:semibold t/font-weights)
                               :color t/text-primary}}
                 (:name user)]
                [:div {:style {:font-family t/font-mono :font-size "11px"
                               :color t/text-tertiary :margin-top "1px"}}
                 (:email user)]]
               [:span {:style (merge {:font-family t/font-mono :font-size "10px"
                                      :padding "2px 8px"
                                      :border-radius (:full t/border-radius)
                                      :font-weight (:semibold t/font-weights)
                                      :letter-spacing "0.04em"
                                      :text-transform "uppercase"}
                                     (role-badge-style (:role user)))}
                (or (:role user) "SEM ROLE")]])])])})))

(defn- brand-panel []
  [:div {:style {:position "relative" :padding "64px"
                 :display "flex" :flex-direction "column" :justify-content "space-between"
                 :background t/color-night :color t/color-white :overflow "hidden"}}
   ;; Subtle dot grid (matches .dot-grid in pipo-design.css)
   [:div {:class "dot-grid"}]
   ;; Cyan radial flourish (background)
   [:div {:style {:position "absolute" :inset "0"
                  :background (str "radial-gradient(circle at 30% 70%," t/color-cyan " 0%,transparent 60%)")
                  :opacity "0.18" :pointer-events "none"}}]
   ;; Brand mark
   [:div {:style {:position "relative" :z-index 1 :display "flex" :gap "14px" :align-items "center"}}
    [:div {:style {:width "42px" :height "42px" :border-radius "12px"
                   :background t/color-white :color t/color-primary
                   :display "flex" :align-items "center" :justify-content "center"
                   :font-family t/font-display :font-size "26px" :line-height "1"}}
     "P"]
    [:div
     [:strong {:style {:font-family t/font-heading :font-size "17px"
                       :font-weight (:semibold t/font-weights)}}
      "Pipo Saúde"]
     [:div {:style {:font-family t/font-mono :font-size "11px"
                    :color "rgba(255,255,255,0.6)" :letter-spacing "0.04em"}}
      "plataforma · rv"]]]
   ;; Hero copy
   [:div {:style {:position "relative" :z-index 1 :max-width "440px"}}
    [:div {:style {:font-family t/font-mono :font-size "11px" :color t/color-cyan
                   :text-transform "uppercase" :letter-spacing "0.08em"
                   :margin-bottom "14px"}}
     "plataforma rv · q2/2026"]
    [:h1 {:style {:font-family t/font-display :font-size "64px" :font-weight "400"
                  :line-height "1.05" :color t/color-white
                  :letter-spacing "-0.015em" :margin 0}}
     "Comissões"
     [:br]
     "com clareza."]
    [:p {:style {:font-size "15px" :color "rgba(255,255,255,0.7)"
                 :margin-top "18px" :line-height "1.5"}}
     "Apuração, validação e pagamento de remuneração variável para times de vendas — todo o ciclo, do cálculo ao depósito."]]
   ;; Footer
   [:div {:style {:position "relative" :z-index 1
                  :font-family t/font-mono :font-size "11px"
                  :color "rgba(255,255,255,0.5)"}}
    "© 2026 Pipo Saúde"]])

(defn login-page []
  (let [loading? @(rf/subscribe [:auth/loading?])
        error    @(rf/subscribe [:auth/error])]
    [:div {:style {:min-height "100vh"
                   :display "grid"
                   :grid-template-columns "1fr 1fr"
                   :background t/color-night
                   :font-family t/font-body}}
     ;; Left brand pane
     [brand-panel]

     ;; Right form pane
     [:div {:style {:background t/bg-card :color t/text-secondary
                    :padding "64px 72px"
                    :display "flex" :flex-direction "column" :justify-content "center" :gap "24px"
                    :overflow-y "auto"}}
      [:div
       [:div {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary
                      :text-transform "uppercase" :letter-spacing "0.06em"
                      :margin-bottom "8px"}}
        "entrar"]
       [:h2 {:style {:font-family t/font-display :font-weight "400" :font-size "34px"
                     :color t/text-primary :margin 0 :letter-spacing "-0.005em"}}
        "Bem-vindo de volta"]
       [:p {:style {:font-size "13px" :color t/text-tertiary :margin-top "6px"}}
        "Use seu e-mail corporativo para acessar."]]

      (when error
        [:div {:style {:background t/error-light :color t/error-dark
                       :padding "12px 14px" :border-radius (:sm t/border-radius)
                       :border (str "1px solid " t/error-default)
                       :font-size "13px"}}
         error])

      ;; Google SSO button (production)
      [btn/button {:variant    :primary
                   :size       :lg
                   :full-width true
                   :loading    loading?
                   :on-click   #(js/console.log "Google SSO — configure GOOGLE_CLIENT_ID")}
       "Entrar com SSO Google"]

      ;; Dev login picker
      [dev-login-picker]]]))
