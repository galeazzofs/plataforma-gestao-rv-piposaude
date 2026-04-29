(ns app.views.revops.appraisal
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(defn new-appraisal-modal [_]
  (let [form (r/atom {:quarter "1" :year "2026"})]
    (fn [{:keys [open? on-close]}]
      [modal/modal {:open? open? :on-close on-close :title "Nova Apuração" :size :sm}
       [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
        [inputs/select
         {:label     "Trimestre"
          :value     (:quarter @form)
          :options   [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                      {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
          :on-change #(swap! form assoc :quarter %)}]
        [inputs/select
         {:label     "Ano"
          :value     (:year @form)
          :options   [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
          :on-change #(swap! form assoc :year %)}]
        [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
         [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
         [btn/button {:variant :primary
                      :on-click (fn []
                                  (rf/dispatch [:revops/create-appraisal @form])
                                  (on-close))}
          "Criar"]]]])))

(defn status-indicator [status]
  (let [steps ["DRAFT" "CALCULATING" "REVIEWING" "VALIDATING" "APPROVED" "LOCKED"]
        current-idx (.indexOf (clj->js steps) status)]
    [:div {:style {:display "flex" :align-items "center" :gap "4px"}}
     (map-indexed
      (fn [idx step]
        ^{:key step}
        [:div {:style {:display "flex" :align-items "center" :gap "4px"}}
         [:div {:style {:width "8px" :height "8px" :border-radius (:full t/border-radius)
                        :background (cond
                                      (< idx current-idx) t/success-default
                                      (= idx current-idx) t/color-primary
                                      :else t/border-default)}}]
         (when (< idx (dec (count steps)))
           [:div {:style {:width "16px" :height "1px"
                          :background (if (< idx current-idx) t/success-default t/border-default)}}])])
      steps)]))

(defn- delete-btn [id]
  [btn/button {:variant  :danger :size :sm
               :on-click (fn [e]
                           (.stopPropagation e)
                           (when (js/confirm "Tem certeza? Isso vai apagar a apuração e resetar todos os matches de NFs.")
                             (rf/dispatch [:revops/delete-appraisal id])))}
   "Deletar"])

(defn step-actions [appraisal]
  (let [status (:status appraisal)
        id     (:id appraisal)]
    [:div {:style {:display "flex" :gap "6px" :align-items "center"}}
     (case status
       "DRAFT"
       [:<>
        [btn/button {:variant  :primary :size :sm
                     :on-click #(rf/dispatch [:revops/run-appraisal id])}
         "Iniciar Calculo"]
        [delete-btn id]]

       "CALCULATING"
       [:<>
        [btn/button {:variant  :primary :size :sm
                     :on-click #(rf/dispatch [:navigate! [:revops/appraisal-review {:id id}]])}
         "Revisar Calculo"]
        [delete-btn id]]

       "REVIEWING"
       [:<>
        [btn/button {:variant  :primary :size :sm
                     :on-click #(rf/dispatch [:navigate! [:revops/appraisal-review {:id id}]])}
         "Revisar Valores"]
        [delete-btn id]]

       "VALIDATING"
       [:<>
        [:span {:style {:color t/text-secondary :font-size (:xs t/font-sizes)
                        :display "flex" :align-items "center" :gap "4px"}}
         "Aguardando EVs"]
        [delete-btn id]]

       "APPROVED"
       [:<>
        [btn/button {:variant  :primary :size :sm
                     :on-click #(rf/dispatch [:revops/approve-appraisal-payment id])}
         "Liberar Pagamento"]
        [delete-btn id]]

       "LOCKED"
       nil

       [delete-btn id])]))

(def appraisal-columns
  [{:key :period :label "Período" :sortable false :width "100px"
    :render (fn [row] [:span {:style {:font-weight (:semibold t/font-weights)}}
                       (str "Q" (:quarter row) "/" (:year row))])}
   {:key :status :label "Status" :sortable false :width "130px"
    :render (fn [row] [badge/status-badge {:status (:status row)}])}
   {:key :ev_count  :label "EVs" :sortable false :align "center" :width "60px"}
   {:key :actions   :label "Ações" :sortable false
    :render step-actions}])

(defn appraisal-page []
  (rf/dispatch [:revops/fetch-appraisals])
  (let [modal-open? (r/atom false)]
    (fn []
      (let [appraisals @(rf/subscribe [:revops/appraisals])
            loading?   @(rf/subscribe [:revops/appraisal-loading?])
            user       @(rf/subscribe [:auth/current-user])
            route      @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Apuração"
          :subtitle      "Controle do fluxo de apuração de comissões"
          :header-actions
          [btn/button {:variant :primary :on-click #(reset! modal-open? true)}
           "+ Nova Apuração"]}

         [cards/card {}
          [tbl/data-table
           {:columns       appraisal-columns
            :rows          (or appraisals [])
            :empty-message (if loading? "Carregando..." "Nenhuma apuração encontrada")}]]

         [new-appraisal-modal {:open? @modal-open? :on-close #(reset! modal-open? false)}]]))))
