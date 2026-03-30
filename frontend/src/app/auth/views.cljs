(ns app.auth.views
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.tokens :as t]
            [app.ds.buttons :as btn]))

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
      [:div {:style {:margin-top "24px"
                     :text-align "left"}}
       [:div {:style {:font-size (:xs t/font-sizes)
                      :color t/text-secondary
                      :text-transform "uppercase"
                      :letter-spacing "0.05em"
                      :margin-bottom "12px"
                      :font-weight (:medium t/font-weights)}}
        "Dev Login — selecione um usuario:"]
       (if @loading?
         [:div {:style {:text-align "center" :padding "16px" :color t/text-disabled}} "Carregando..."]
         (for [user @users]
           ^{:key (:email user)}
           [:div {:style {:display "flex"
                          :justify-content "space-between"
                          :align-items "center"
                          :padding "10px 12px"
                          :margin-bottom "4px"
                          :border-radius (:md t/border-radius)
                          :border (str "1px solid " t/border-default)
                          :cursor "pointer"
                          :transition t/transition-fast}
                  :on-click #(rf/dispatch [:auth/dev-login (:email user)])}
            [:div
             [:div {:style {:font-size (:sm t/font-sizes)
                            :font-weight (:medium t/font-weights)
                            :color t/text-primary}}
              (:name user)]
             [:div {:style {:font-size (:xs t/font-sizes)
                            :color t/text-secondary}}
              (:email user)]]
            [:span {:style {:font-size (:xs t/font-sizes)
                            :padding "2px 8px"
                            :border-radius (:full t/border-radius)
                            :font-weight (:medium t/font-weights)
                            :background (case (:role user)
                                          "ADMIN" t/color-primary
                                          "FINANCE" t/blue-500
                                          "GERENTE" t/purple-700
                                          "EV" t/success-default
                                          "CN" t/peach-400
                                          t/bg-subtle)
                            :color (if (= (:role user) nil)
                                     t/text-secondary
                                     t/color-white)}}
             (or (:role user) "SEM ROLE")]]))])))

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
                    :width         "440px"}}
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
      ;; Google SSO button (production)
      [btn/button {:variant    :secondary
                   :size       :lg
                   :full-width true
                   :loading    loading?
                   :on-click   #(js/console.log "Google SSO — configure GOOGLE_CLIENT_ID")}
       "Entrar com Google"]
      ;; Dev login picker
      [dev-login-picker]]]))
