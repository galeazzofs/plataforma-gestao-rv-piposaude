(ns app.views.ev.validation
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.cards :as cards]
            [app.ds.tokens :as t]
            [app.auth.subs]))

(def sidebar-items
  [{:key :ev/dashboard  :label "Dashboard"  :icon "📊" :route :ev/dashboard}
   {:key :ev/history    :label "Histórico"  :icon "📅" :route :ev/history}
   {:key :ev/validation :label "Validação"  :icon "✓"  :route :ev/validation}])

(defn fmt-brl [v]
  (when v
    (str "R$ " (.toLocaleString v "pt-BR" #js {:minimumFractionDigits 2 :maximumFractionDigits 2}))))

(def columns
  [{:key :client_name        :label "Cliente"       :sortable true}
   {:key :benefit_type       :label "Benefício"     :sortable false}
   {:key :mrr                :label "MRR"           :sortable true  :align "right"
    :render (fn [row] (fmt-brl (:mrr row)))}
   {:key :commission_monthly :label "Comissão/mês"  :sortable true  :align "right"
    :render (fn [row] (fmt-brl (:commission_monthly row)))}
   {:key :status             :label "Status"        :sortable false :width "120px"
    :render (fn [row] [badge/status-badge {:status (:status row)}])}])

(defn contest-modal [{:keys [open? on-close on-submit deal-id]}]
  (let [comment (r/atom "")]
    (fn []
      [modal/modal {:open?    open?
                    :on-close on-close
                    :title    "Contestar negócio"
                    :size     :md}
       [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
        [:p {:style {:color t/text-secondary :margin "0" :font-size (:sm t/font-sizes) :line-height "1.6"}}
         "Descreva o motivo da contestação. Sua mensagem será enviada ao RevOps para análise."]
        [inputs/input
         {:label       "Comentário"
          :value       @comment
          :placeholder "Ex: O MRR calculado está incorreto porque..."
          :on-change   #(reset! comment %)
          :required    true}]
        [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
         [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
         [btn/button {:variant  :danger
                      :disabled (clojure.string/blank? @comment)
                      :on-click #(do (on-submit deal-id @comment)
                                     (reset! comment "")
                                     (on-close))}
          "Contestar"]]]])))

(defn validation-page []
  (rf/dispatch [:ev/fetch-validations])
  (let [contest-open?   (r/atom false)
        contest-deal-id (r/atom nil)]
    (fn []
      (let [validations @(rf/subscribe [:ev/validations])
            loading?    @(rf/subscribe [:ev/loading?])
            user        @(rf/subscribe [:auth/current-user])
            route       @(rf/subscribe [:current-route-name])
            action-cols (conj columns
                              {:key    :actions
                               :label  "Ações"
                               :width  "140px"
                               :render (fn [row]
                                         (let [status (:status row)
                                               pending? (= status "PENDING")]
                                           [:div {:style {:display "flex" :gap "6px"}}
                                            (when pending?
                                              [btn/button
                                               {:variant  :primary
                                                :size     :sm
                                                :on-click #(rf/dispatch [:ev/approve-validation (:id row)])}
                                               "Aprovar"])
                                            (when pending?
                                              [btn/button
                                               {:variant  :danger
                                                :size     :sm
                                                :on-click #(do (reset! contest-deal-id (:id row))
                                                               (reset! contest-open? true))}
                                               "Contestar"])]))})]
        [layout/page-shell
         {:sidebar-items sidebar-items
          :current-route route
          :user          user
          :title         "Validação"
          :subtitle      "Revise e aprove ou conteste os negócios calculados"}

         [cards/card {}
          [:div {:style {:display "flex" :justify-content "space-between" :align-items "center" :margin-bottom "16px"}}
           [:div
            [:h3 {:style {:font-size (:base t/font-sizes) :font-weight (:semibold t/font-weights)
                          :margin "0" :color t/text-primary}} "Negócios para Validação"]
            [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}}
             (str (count (or validations [])) " itens pendentes")]]]
          [tbl/data-table
           {:columns       action-cols
            :rows          (or validations [])
            :empty-message (if loading? "Carregando..." "Nenhuma validação pendente")}]]

         [contest-modal {:open?     @contest-open?
                          :on-close  #(reset! contest-open? false)
                          :on-submit (fn [id comment]
                                       (rf/dispatch [:ev/contest-validation id comment]))
                          :deal-id   @contest-deal-id}]]))))
