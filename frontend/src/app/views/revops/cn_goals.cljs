(ns app.views.revops.cn-goals
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.ds.table :as tbl]))

;; ── Events ──────────────────────────────────────────────────────────────────

(rf/reg-event-fx
 :revops/fetch-cn-goals
 (fn [{:keys [db]} [_ month year]]
   {:db   (assoc-in db [:admin :cn-goals-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-goals "?month=" month "&year=" year)
           :on-success [:revops/cn-goals-loaded]
           :on-failure [:revops/cn-goals-error]}}))

(rf/reg-event-db
 :revops/cn-goals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :cn-goals] (:data response))
       (assoc-in [:admin :cn-goals-loading?] false))))

(rf/reg-event-db
 :revops/cn-goals-error
 (fn [db _] (assoc-in db [:admin :cn-goals-loading?] false)))

(rf/reg-event-fx
 :revops/save-cn-goals
 (fn [_ [_ payload]]
   {:http {:method     :put
           :url        ep/cn-goals
           :body       payload
           :on-success [:revops/cn-goals-saved (:month payload) (:year payload)]
           :on-failure [:revops/cn-goals-error]}}))

(rf/reg-event-fx
 :revops/cn-goals-saved
 (fn [_ [_ month year _response]]
   {:dispatch [:revops/fetch-cn-goals month year]}))

;; ── Subs ─────────────────────────────────────────────────────────────────────

(rf/reg-sub :revops/cn-goals (fn [db _] (get-in db [:admin :cn-goals] [])))
(rf/reg-sub :revops/cn-goals-loading? (fn [db _] (get-in db [:admin :cn-goals-loading?])))

;; ── View ─────────────────────────────────────────────────────────────────────

(defn page []
  (let [filter-state (r/atom {:month "4" :year "2026"})
        edits        (r/atom {})]
    (fn []
      (let [goals    @(rf/subscribe [:revops/cn-goals])
            loading? @(rf/subscribe [:revops/cn-goals-loading?])]
        [layout/page {:title "Metas Mensais CN"}
         [cards/card
          [:div {:style {:display "flex" :gap "12px" :align-items "flex-end" :margin-bottom "16px"}}
           [inputs/select
            {:label "Mês" :value (:month @filter-state)
             :options (map (fn [m] {:value (str m) :label (str m)}) (range 1 13))
             :on-change #(swap! filter-state assoc :month %)}]
           [inputs/select
            {:label "Ano" :value (:year @filter-state)
             :options [{:value "2026" :label "2026"} {:value "2025" :label "2025"}]
             :on-change #(swap! filter-state assoc :year %)}]
           [btn/button {:variant :secondary
                        :on-click #(rf/dispatch [:revops/fetch-cn-goals
                                                 (:month @filter-state)
                                                 (:year @filter-state)])}
            "Buscar"]]
          [tbl/table
           {:loading? loading?
            :columns  [{:key :cn_id    :label "CN"}
                       {:key :sao_target :label "Meta SAO"
                        :render (fn [v row]
                                  [inputs/text-field
                                   {:value    (get-in @edits [(:cn_id row) :sao_target] (str v))
                                    :on-change #(swap! edits assoc-in [(:cn_id row) :sao_target] %)}])}
                       {:key :vidas_target :label "Meta Vidas"
                        :render (fn [v row]
                                  [inputs/text-field
                                   {:value    (get-in @edits [(:cn_id row) :vidas_target] (str v))
                                    :on-change #(swap! edits assoc-in [(:cn_id row) :vidas_target] %)}])}]
            :rows     goals}]
          [btn/button
           {:variant  :primary
            :on-click (fn []
                        (let [items (mapv (fn [[cn-id vals]]
                                           (merge {:cn_id cn-id} vals))
                                         @edits)]
                          (rf/dispatch [:revops/save-cn-goals
                                        {:month (:month @filter-state)
                                         :year  (:year @filter-state)
                                         :items items}])))}
           "Salvar Metas"]]]))))
