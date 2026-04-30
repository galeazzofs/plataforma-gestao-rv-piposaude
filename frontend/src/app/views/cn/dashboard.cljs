(ns app.views.cn.dashboard
  (:require [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.tokens :as t]
            [app.auth.subs]))

(def sidebar-items
  [{:key :cn/dashboard  :label "Apurações" :icon "📊" :route :cn/dashboard}
   {:key :cn/simulator  :label "Simulador" :icon "🧮" :route :cn/simulator}
   {:key :ev/dashboard  :label "Dashboard" :icon "📈" :route :ev/dashboard}
   {:key :ev/history    :label "Histórico" :icon "📅" :route :ev/history}
   {:key :ev/validation :label "Validação" :icon "✓"  :route :ev/validation}])

;; ── Events ──────────────────────────────────────────────────────────────────

(rf/reg-event-fx
 :cn/fetch-appraisals
 (fn [{:keys [db]} _]
   {:db   (assoc-in db [:cn :appraisals-loading?] true)
    :http {:method     :get
           :url        ep/cn-appraisal
           :on-success [:cn/appraisals-loaded]
           :on-failure [:cn/appraisals-error]}}))

(rf/reg-event-db
 :cn/appraisals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:cn :appraisals] (:data response))
       (assoc-in [:cn :appraisals-loading?] false))))

(rf/reg-event-db
 :cn/appraisals-error
 (fn [db _] (assoc-in db [:cn :appraisals-loading?] false)))

;; ── Subs ─────────────────────────────────────────────────────────────────────

(rf/reg-sub :cn/appraisals (fn [db _] (get-in db [:cn :appraisals] [])))
(rf/reg-sub :cn/appraisals-loading? (fn [db _] (get-in db [:cn :appraisals-loading?])))

;; ── View ─────────────────────────────────────────────────────────────────────

(defn page []
  (rf/dispatch [:cn/fetch-appraisals])
  (fn []
    (let [items    @(rf/subscribe [:cn/appraisals])
          loading? @(rf/subscribe [:cn/appraisals-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])]
      [layout/page-shell
       {:sidebar-items sidebar-items
        :current-route route
        :user          user
        :title         "Minhas Apurações"}
       (if loading?
         [:div {:style {:padding "48px" :text-align "center" :color t/text-secondary}}
          "Carregando..."]
         [tbl/data-table
          {:columns [{:key :month       :label "Mês"}
                     {:key :year        :label "Ano"}
                     {:key :score_final :label "Score"}
                     {:key :multiplicador :label "Mult."}
                     {:key :commission_amount :label "Comissão (R$)"}
                     {:key :is_final    :label "Status"
                      :render (fn [row]
                                (if (:is_final row)
                                  [badge/badge {:variant :success} "Final"]
                                  [badge/badge {:variant :warning} "Rascunho"]))}]
           :rows    items}])])))
