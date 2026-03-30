(ns app.views.revops.settings
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn toggle-field [{:keys [label description value on-change]}]
  [:div {:style {:display "flex" :justify-content "space-between" :align-items "flex-start"
                 :padding "16px 0" :border-bottom (str "1px solid " t/bg-subtle)}}
   [:div
    [:div {:style {:font-size (:sm t/font-sizes) :font-weight (:medium t/font-weights)}} label]
    (when description
      [:div {:style {:font-size (:xs t/font-sizes) :color t/text-secondary :margin-top "2px"}} description])]
   [:label {:style {:position "relative" :display "inline-block" :width "44px" :height "24px" :cursor "pointer"}}
    [:input {:type      "checkbox"
             :checked   (boolean value)
             :style     {:opacity "0" :width "0" :height "0"}
             :on-change #(on-change (.. % -target -checked))}]
    [:span {:style {:position "absolute" :cursor "pointer" :inset "0"
                    :background (if value t/color-primary t/border-default)
                    :border-radius (:full t/border-radius)
                    :transition t/transition-fast}}
     [:span {:style {:position "absolute" :content "''"
                     :height "18px" :width "18px"
                     :left (if value "23px" "3px")
                     :bottom "3px"
                     :background t/color-white
                     :border-radius (:full t/border-radius)
                     :transition t/transition-fast}}]]]])

(defn settings-page []
  (rf/dispatch [:revops/fetch-settings])
  (let [local-settings (r/atom nil)]
    (fn []
      (let [settings @(rf/subscribe [:revops/settings])
            loading? @(rf/subscribe [:revops/settings-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            form     (or @local-settings settings {})]

        ;; Sync local state once loaded
        (when (and settings (nil? @local-settings))
          (reset! local-settings settings))

        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Configurações"
          :subtitle      "Parâmetros globais da plataforma"
          :header-actions
          [btn/button {:variant  :primary
                       :loading  loading?
                       :on-click #(rf/dispatch [:revops/save-settings @local-settings])}
           "Salvar Configurações"]}

         [cards/card {}
          (if (and loading? (nil? settings))
            [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}} "Carregando..."]
            [:div {:style {:display "flex" :flex-direction "column"}}

             ;; Deadlines section
             [:h4 {:style {:font-size (:base t/font-sizes) :font-weight (:semibold t/font-weights)
                            :margin "0 0 16px"}} "Prazos"]
             [:div {:style {:display "grid" :grid-template-columns "1fr 1fr" :gap "16px" :margin-bottom "32px"}}
              [inputs/input
               {:label     "Prazo de Validação (dias)"
                :type      "number"
                :value     (str (or (:validation_deadline_days form) ""))
                :on-change #(swap! local-settings assoc :validation_deadline_days (js/parseInt %))}]
              [inputs/input
               {:label     "Intervalo de Sync (horas)"
                :type      "number"
                :value     (str (or (:sync_interval_hours form) ""))
                :on-change #(swap! local-settings assoc :sync_interval_hours (js/parseInt %))}]]

             ;; Notifications section
             [:h4 {:style {:font-size (:base t/font-sizes) :font-weight (:semibold t/font-weights)
                            :margin "0 0 8px"}} "Notificações"]
             [toggle-field
              {:label       "Notificar EVs na abertura de validação"
               :description "Envia e-mail quando o período de validação iniciar"
               :value       (:notify_ev_validation_open form)
               :on-change   #(swap! local-settings assoc :notify_ev_validation_open %)}]
             [toggle-field
              {:label       "Notificar Finance na aprovação"
               :description "Envia e-mail quando uma apuração for aprovada para pagamento"
               :value       (:notify_finance_approval form)
               :on-change   #(swap! local-settings assoc :notify_finance_approval %)}]
             [toggle-field
              {:label       "Notificar RevOps em erros de sync"
               :description "Alerta quando a sincronização com HubSpot falhar"
               :value       (:notify_revops_sync_error form)
               :on-change   #(swap! local-settings assoc :notify_revops_sync_error %)}]])]]))))
