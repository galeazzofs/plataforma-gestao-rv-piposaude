(ns app.views.cn.dashboard
  (:require [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; CN · Dashboard de apurações — design layout: KPIs + table.

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

;; ── Subs ────────────────────────────────────────────────────────────────────

(rf/reg-sub :cn/appraisals (fn [db _] (get-in db [:cn :appraisals] [])))
(rf/reg-sub :cn/appraisals-loading? (fn [db _] (get-in db [:cn :appraisals-loading?])))

;; ── Helpers ─────────────────────────────────────────────────────────────────

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct [v]
  (when v (-> v js/parseFloat (* 100) (.toFixed 0))))

(defn- mult [v]
  (when v (-> v js/parseFloat (.toFixed 2)
              (clojure.string/replace "." ","))))

(defn page []
  (rf/dispatch [:cn/fetch-appraisals])
  (fn []
    (let [items    @(rf/subscribe [:cn/appraisals])
          loading? @(rf/subscribe [:cn/appraisals-loading?])
          user     @(rf/subscribe [:auth/current-user])
          route    @(rf/subscribe [:current-route-name])
          rows     (or items [])
          total    (reduce + 0 (map #(or (:commission_amount %) 0) rows))
          months   (count rows)
          finals   (count (filter :is_final rows))
          avg-pct  (when (seq rows)
                     (-> (/ (reduce + 0 (map #(or (:score_final %) 0) rows))
                            (count rows))
                         (* 100)))]
      [layout/page-shell
       {:current-route route :user user
        :crumbs ["plataforma rv" "cn" "apurações"]
        :title "Minhas Apurações"
        :subtitle (str months " ciclos · " finals " finalizados")
        :header-actions
        [[:button.btn.btn-secondary
          {:on-click #(rf/dispatch [:navigate :cn/simulator])}
          [layout/icon "target" {:width 14 :height 14}] "Simulador"]]}

       ;; KPIs
       [:div.kpi-grid.-three
        [:div.kpi
         [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "total apurado"]
         [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "·")]
         [:div.kpi-foot (str months " ciclos")]]
        [:div.kpi
         [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "score médio"]
         [:div.kpi-value (str (or (some-> avg-pct (.toFixed 0)) "·"))
          [:span.frac "%"]]]
        [:div.kpi
         [:div.kpi-label [layout/icon "check" {:width 14 :height 14}] "ciclos finais"]
         [:div.kpi-value (str finals)]
         [:div.kpi-foot (str (- months finals) " em rascunho")]]]

       ;; Table
       [:div.card {:style {:padding 0}}
        [:div {:style {:padding "18px 20px 0"}}
         [:h3 "Apurações mensais"]
         [:div.card-sub "Score, multiplicador e valor final por mês"]]
        [:table.table
         [:thead
          [:tr
           [:th "Período"]
           [:th.center "Score"]
           [:th.right "Multipl."]
           [:th.right "Comissão"]
           [:th "Status"]]]
         [:tbody
          (cond
            loading?
            [:tr [:td {:col-span 5 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                  "Carregando…"]]

            (empty? rows)
            [:tr [:td {:col-span 5 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                  "Nenhuma apuração disponível"]]

            :else
            (for [r rows]
              ^{:key (str (:year r) "-" (:month r))}
              [:tr
               [:td.name.num (str (:month r) "/" (:year r))]
               [:td.center.num (str (or (pct (:score_final r)) "·") "%")]
               [:td.right.num (str (or (mult (:multiplicador r)) "·") "x")]
               [:td.right.strong-num (str "R$ " (or (fmt-int (:commission_amount r)) "·"))]
               [:td (if (:is_final r)
                      [:span.badge.badge-paid "Final"]
                      [:span.badge.badge-review "Rascunho"])]]))]]]])))
