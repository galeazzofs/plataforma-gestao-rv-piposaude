(ns app.views.revops.goals
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.auth.subs]))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- goal-row []
  (let [editing? (r/atom false)
        value    (r/atom 0)]
    (fn [{:keys [row on-edit]}]
      [:tr
       [:td.name (:ev_name row)]
       [:td [:span.badge.badge-locked (str "Q" (:quarter row) "/" (:year row))]]
       [:td.right
        (if @editing?
          [:input.field-input
           {:type "number"
            :style {:width "140px" :text-align "right" :padding "6px 10px"}
            :value @value
            :on-change #(reset! value (js/parseFloat (.. % -target -value)))}]
          [:span.strong-num (str "R$ " (or (fmt-int (:amount row)) "·"))])]
       [:td.right
        (if @editing?
          [:<>
           [:button.btn.btn-primary.btn-sm
            {:on-click (fn []
                         (on-edit (:id row) {:amount @value})
                         (reset! editing? false))}
            "Salvar"]
           " "
           [:button.btn.btn-secondary.btn-sm
            {:on-click #(reset! editing? false)} "Cancelar"]]
          [:button.btn.btn-ghost.btn-sm
           {:on-click #(do (reset! value (or (:amount row) 0)) (reset! editing? true))}
           [layout/icon "edit" {:width 12 :height 12}] " Editar"])]])))

(defn- new-goal-modal []
  (let [form (r/atom {:ev_id "" :quarter "" :year "" :mrr_target ""})]
    (fn [{:keys [open? on-close users]}]
      (let [quarter-opts [{:value "" :label "Selecione"}
                          {:value "1" :label "Q1"} {:value "2" :label "Q2"}
                          {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
            ev-opts (into [{:value "" :label "Selecione o EV"}]
                          (map #(hash-map :value (str (:id %)) :label (:name %))
                               (filter #(#{"EV" "CN"} (:role %)) (or users []))))]
        [modal/modal {:open? open? :on-close on-close
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
                        :disabled (or (str/blank? (:ev_id @form))
                                      (str/blank? (:quarter @form))
                                      (str/blank? (:year @form))
                                      (str/blank? (:mrr_target @form)))
                        :on-click (fn []
                                    (rf/dispatch [:revops/create-goal
                                                  {:ev_id (:ev_id @form)
                                                   :quarter (js/parseInt (:quarter @form))
                                                   :year (js/parseInt (:year @form))
                                                   :mrr_target (js/parseFloat (:mrr_target @form))}])
                                    (on-close))}
            "Criar Meta"]]]]))))

(defn goals-page []
  (rf/dispatch [:revops/fetch-goals])
  (rf/dispatch [:revops/fetch-users])
  (let [modal-open? (r/atom false)]
    (fn []
      (let [goals    @(rf/subscribe [:revops/goals])
            loading? @(rf/subscribe [:revops/goals-loading?])
            users    @(rf/subscribe [:revops/users])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            total    (reduce + 0 (map #(or (:amount %) 0) (or goals [])))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "metas"]
          :title "Metas"
          :subtitle (str (count (or goals [])) " metas configuradas")
          :header-actions
          [[:label.btn.btn-secondary {:style {:cursor "pointer"}}
            [layout/icon "upload" {:width 14 :height 14}] "Importar XLSX"
            [:input {:type "file" :accept ".xlsx,.xls" :style {:display "none"}
                     :on-change (fn [e]
                                  (when-let [f (-> e .-target .-files (aget 0))]
                                    (rf/dispatch [:revops/import-goals f])))}]]
           [:button.btn.btn-primary
            {:on-click #(reset! modal-open? true)}
            [layout/icon "plus" {:width 14 :height 14}] "Nova meta"]]}

         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "metas configuradas"]
           [:div.kpi-value (str (count (or goals [])))]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "MRR meta total"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "·")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "EVs com meta"]
           [:div.kpi-value (str (count (distinct (map :ev_id (or goals [])))))]]]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "EV"]
             [:th "Período"]
             [:th.right "Valor (Meta)"]
             [:th.right "Ações"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 4 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? goals)
              [:tr [:td {:col-span 4 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma meta encontrada · crie a primeira para começar"]]

              :else
              (for [g goals]
                ^{:key (:id g)}
                [goal-row {:row g
                           :on-edit (fn [id payload]
                                      (rf/dispatch [:revops/update-goal id payload]))}]))]]]

         [new-goal-modal {:open? @modal-open?
                          :on-close #(reset! modal-open? false)
                          :users users}]]))))
