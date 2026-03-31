(ns app.auth.views
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

(defn role-badge-style [role]
  (case role
    "ADMIN"    {:background t/color-primary :color t/color-white}
    "FINANCE"  {:background t/blue-700 :color t/color-white}
    "GERENTE"  {:background t/purple-700 :color t/color-white}
    "EV"       {:background t/success-default :color t/color-white}
    "CN"       {:background t/beige-500 :color t/color-white}
    {:background t/bg-subtle :color t/text-secondary}))

(defn dev-login-picker
  "Dev-only: shows a list of seeded users to login as."
  []
  (let [users (r/atom nil)
        loading? (r/atom true)]
    ;; Fetch available users on mount
    (-> (js/fetch "http://localhost:5000/api/v1/auth/dev-users")
        (.then #(.json %))
        (.then (fn [data]
                 (reset! users (js->clj (.-data data) :keywordize-keys true))
                 (reset! loading? false)))
        (.catch (fn [_]
                  (reset! loading? false))))
    (fn []
      [:div
       ;; Separator
       [:div {:style {:display "flex" :align-items "center" :gap "12px" :margin "24px 0 20px"}}
        [:div {:style {:flex "1" :height "1px" :background t/border-default}}]
        [:span {:style {:font-size (:xs t/font-sizes) :color t/text-disabled
                        :text-transform "uppercase" :letter-spacing "0.08em"
                        :white-space "nowrap"}} "Acesso de Desenvolvimento"]
        [:div {:style {:flex "1" :height "1px" :background t/border-default}}]]

       (if @loading?
         [:div {:style {:text-align "center" :padding "20px" :color t/text-disabled
                        :font-size (:sm t/font-sizes)}} "Carregando usuários..."]
         [:div {:style {:display "flex" :flex-direction "column" :gap "8px"}}
          (for [user @users]
            ^{:key (:email user)}
            [:div {:style {:display "flex"
                           :justify-content "space-between"
                           :align-items "center"
                           :padding "12px 14px"
                           :border-radius (:md t/border-radius)
                           :border (str "1px solid " t/border-default)
                           :cursor "pointer"
                           :transition (str "all " t/transition-fast)
                           :background t/bg-card}
                   :on-click #(rf/dispatch [:auth/dev-login (:email user)])}
             [:div
              [:div {:style {:font-size (:sm t/font-sizes)
                             :font-weight (:semibold t/font-weights)
                             :color t/text-primary}}
               (:name user)]
              [:div {:style {:font-size (:xs t/font-sizes)
                             :color t/text-secondary
                             :margin-top "1px"}}
               (:email user)]]
             [:span {:style (merge {:font-size (:xs t/font-sizes)
                                    :padding "3px 10px"
                                    :border-radius (:full t/border-radius)
                                    :font-weight (:semibold t/font-weights)
                                    :letter-spacing "0.02em"}
                                   (role-badge-style (:role user)))}
              (or (:role user) "SEM ROLE")]])])])))

(defn login-page []
  (let [loading? @(rf/subscribe [:auth/loading?])
        error    @(rf/subscribe [:auth/error])]
    [:div {:style {:min-height       "100vh"
                   :display          "flex"
                   :align-items      "center"
                   :justify-content  "center"
                   :background       (str "linear-gradient(135deg, " t/bg-main " 0%, " t/beige-100 " 100%)")}}
     [:div {:style {:background    t/bg-card
                    :padding       "52px 48px 48px"
                    :border-radius (:xl t/border-radius)
                    :box-shadow    (:lg t/shadows)
                    :border        (str "1px solid " t/border-default)
                    :width         "480px"
                    :max-width     "calc(100vw - 32px)"}}
      ;; Logo / Brand
      [:div {:style {:text-align "center" :margin-bottom "32px"}}
       [:div {:style {:display "inline-flex" :align-items "center" :justify-content "center"
                      :width "56px" :height "56px" :border-radius (:lg t/border-radius)
                      :background t/color-primary :margin-bottom "16px"}}
        [:span {:style {:color t/color-white :font-size (:xl t/font-sizes) :font-weight (:bold t/font-weights)}} "P"]]
       [:h1 {:style {:font-size     (:2xl t/font-sizes)
                     :font-weight   (:bold t/font-weights)
                     :color         t/color-primary
                     :margin        "0 0 6px"
                     :letter-spacing "-0.02em"}}
        "Pipo Saúde"]
       [:p {:style {:color         t/text-secondary
                    :font-size     (:sm t/font-sizes)
                    :margin        "0"}}
        "Plataforma de Gestão de Comissões"]]

      ;; Error card
      (when error
        [:div {:style {:background    t/error-light
                       :color         t/error-dark
                       :padding       "12px 14px"
                       :border-radius (:md t/border-radius)
                       :border        (str "1px solid " t/error-default)
                       :margin-bottom "20px"
                       :font-size     (:sm t/font-sizes)}}
         error])

      ;; Google SSO button (production)
      [btn/button {:variant    :secondary
                   :size       :lg
                   :full-width true
                   :loading    loading?
                   :on-click   #(js/console.log "Google SSO — configure GOOGLE_CLIENT_ID")}
       [:span {:style {:font-size "18px"}} "G"]
       "Entrar com Google"]

      ;; Dev login picker
      [dev-login-picker]]]))
