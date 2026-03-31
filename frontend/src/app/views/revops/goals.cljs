(ns app.views.revops.goals
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.buttons :as btn]
            [app.ds.inputs :as inputs]
            [app.ds.modal :as modal]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(defn goal-row [{:keys [row on-edit]}]
  (let [editing? (r/atom false)
        value    (r/atom (or (:amount row) 0))]
    (fn []
      [:tr {:style {:border-bottom (str "1px solid " t/border-default)}}
       [:td {:style {:padding "12px 16px" :color t/text-primary}} (:ev_name row)]
       [:td {:style {:padding "12px 16px" :color t/text-secondary :font-size (:sm t/font-sizes)}}
        [:span {:style {:background t/beige-100 :color t/beige-700 :padding "2px 8px"
                        :border-radius (:full t/border-radius) :font-size (:xs t/font-sizes)
                        :font-weight (:semibold t/font-weights)}}
         (str "Q" (:quarter row) "/" (:year row))]]
       [:td {:style {:padding "12px 16px" :text-align "right"}}
        (if @editing?
          [:input {:type      "number"
                   :value     @value
                   :style     {:padding "6px 10px" :border (str "1px solid " t/border-default)
                               :border-radius (:md t/border-radius) :width "140px"
                               :font-size (:sm t/font-sizes) :text-align "right"}
                   :on-change #(reset! value (js/parseFloat (.. % -target -value)))}]
          [:span {:style {:font-weight (:semibold t/font-weights)}} (fmt-brl (:amount row))])]
       [:td {:style {:padding "12px 16px" :text-align "right"}}
        (if @editing?
          [:div {:style {:display "flex" :gap "6px" :justify-content "flex-end"}}
           [btn/button {:variant :primary :size :sm
                        :on-click (fn []
                                    (on-edit (:id row) {:amount @value})
                                    (reset! editing? false))}
            "Salvar"]
           [btn/button {:variant :secondary :size :sm
                        :on-click #(reset! editing? false)}
            "Cancelar"]]
          [btn/button {:variant :ghost :size :sm
                       :on-click #(reset! editing? true)}
           "Editar"])]])))

(defn new-goal-modal [{:keys [open? on-close users]}]
  (let [form (r/atom {:ev_id "" :quarter "" :year "" :mrr_target ""})]
    (fn []
      (let [quarter-opts [{:value "" :label "Selecione"}
                          {:value "1" :label "Q1"} {:value "2" :label "Q2"}
                          {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
            ev-opts (into [{:value "" :label "Selecione o EV"}]
                          (map #(hash-map :value (str (:id %)) :label (:name %))
                               (filter #(#{"EV" "CN"} (:role %)) (or users []))))]
        [app.ds.modal/modal {:open? open? :on-close on-close
                             :title "Nova Meta" :size :sm}
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [inputs/select {:label "EV" :required true
                          :value (:ev_id @form) :options ev-opts
                          :on-change #(swap! form assoc :ev_id %)}]
          [:div {:style {:display "flex" :gap "12px"}}
           [inputs/select {:label "Trimestre" :required true
                           :value (:quarter @form) :options quarter-opts
                           :on-change #(swap! form assoc :quarter %)}]
           [inputs/input {:label "Ano" :required true :type "number"
                          :value (:year @form) :placeholder "2026"
                          :on-change #(swap! form assoc :year %)}]]
          [inputs/input {:label "Meta MRR (R$)" :required true :type "number"
                         :value (:mrr_target @form) :placeholder "50000"
                         :on-change #(swap! form assoc :mrr_target %)}]
          [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
           [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
           [btn/button {:variant :primary
                        :disabled (or (clojure.string/blank? (:ev_id @form))
                                      (clojure.string/blank? (:quarter @form))
                                      (clojure.string/blank? (:year @form))
                                      (clojure.string/blank? (:mrr_target @form)))
                        :on-click (fn []
                                    (rf/dispatch [:revops/create-goal
                                                  {:ev_id      (:ev_id @form)
                                                   :quarter    (js/parseInt (:quarter @form))
                                                   :year       (js/parseInt (:year @form))
                                                   :mrr_target (js/parseFloat (:mrr_target @form))}])
                                    (on-close))}
            "Criar Meta"]]]]))))

(defn goals-table [goals loading?]
  [cards/card {}
   (if loading?
     [:div {:style {:padding "64px" :text-align "center"}}
      [:div {:style {:display "flex" :flex-direction "column" :align-items "center" :gap "8px"}}
       [:span {:style {:font-size "32px"}} "⏳"]
       [:span {:style {:color t/text-secondary}} "Carregando metas..."]]]
     (if (empty? goals)
       [:div {:style {:padding "64px" :text-align "center"}}
        [:div {:style {:display "flex" :flex-direction "column" :align-items "center" :gap "8px"}}
         [:span {:style {:font-size "32px"}} "🎯"]
         [:span {:style {:color t/text-secondary}} "Nenhuma meta encontrada"]
         [:span {:style {:color t/text-disabled :font-size (:xs t/font-sizes)}} "Crie uma meta para começar"]]]
       [:div {:style {:overflow-x "auto"}}
        [:table {:style {:width "100%" :border-collapse "collapse" :font-size (:sm t/font-sizes)}}
         [:thead
          [:tr {:style {:background t/bg-main :border-bottom (str "1px solid " t/border-default)}}
           [:th {:style {:padding "10px 16px" :text-align "left" :color t/text-secondary
                         :font-size (:xs t/font-sizes) :text-transform "uppercase"
                         :letter-spacing "0.06em" :font-weight (:semibold t/font-weights)}} "EV"]
           [:th {:style {:padding "10px 16px" :text-align "left" :color t/text-secondary
                         :font-size (:xs t/font-sizes) :text-transform "uppercase"
                         :letter-spacing "0.06em" :font-weight (:semibold t/font-weights)}} "Período"]
           [:th {:style {:padding "10px 16px" :text-align "right" :color t/text-secondary
                         :font-size (:xs t/font-sizes) :text-transform "uppercase"
                         :letter-spacing "0.06em" :font-weight (:semibold t/font-weights)}} "Valor (Meta)"]
           [:th {:style {:padding "10px 16px" :width "160px"}}]]]
         [:tbody
          (for [g (or goals [])]
            ^{:key (:id g)}
            [goal-row {:row g :on-edit (fn [id payload]
                                          (rf/dispatch [:revops/update-goal id payload]))}])]]]))])

(defn goals-page []
  (rf/dispatch [:revops/fetch-goals])
  (rf/dispatch [:revops/fetch-users])
  (let [modal-open? (r/atom false)]
    (fn []
      (let [goals    @(rf/subscribe [:revops/goals])
            loading? @(rf/subscribe [:revops/goals-loading?])
            users    @(rf/subscribe [:revops/users])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [:<>
         [layout/page-shell
          {:sidebar-items revops-shell/sidebar-items
           :current-route route
           :user          user
           :title         "Metas"
           :subtitle      "Gerenciar metas por EV, trimestre e ano"
           :header-actions
           [:div {:style {:display "flex" :gap "10px" :align-items "center"}}
            [inputs/file-upload
             {:label  "Importar XLSX"
              :accept ".xlsx,.xls"
              :on-file #(rf/dispatch [:revops/import-goals %])}]
            [btn/button {:variant :primary
                         :on-click #(reset! modal-open? true)}
             "+ Nova Meta"]]}
          [goals-table goals loading?]]
         [new-goal-modal {:open?    @modal-open?
                          :on-close #(reset! modal-open? false)
                          :users    users}]]))))
