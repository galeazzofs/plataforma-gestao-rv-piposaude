(ns app.views.revops.cn-appraisal
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))

(rf/reg-event-fx
 :revops/fetch-cn-appraisals
 (fn [{:keys [db]} [_ month year]]
   {:db   (assoc-in db [:admin :cn-appraisals-loading?] true)
    :http {:method     :get
           :url        (str ep/cn-appraisal "?month=" month "&year=" year)
           :on-success [:revops/cn-appraisals-loaded]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-db
 :revops/cn-appraisals-loaded
 (fn [db [_ response]]
   (-> db
       (assoc-in [:admin :cn-appraisals] (:data response))
       (assoc-in [:admin :cn-appraisals-loading?] false))))

(rf/reg-event-db
 :revops/cn-appraisals-error
 (fn [db _] (assoc-in db [:admin :cn-appraisals-loading?] false)))

(rf/reg-event-fx
 :revops/run-cn-appraisal
 (fn [_ [_ payload]]
   {:http {:method     :post
           :url        ep/cn-appraisal
           :body       payload
           :on-success [:revops/cn-appraisal-done (:month payload) (:year payload)]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-event-fx
 :revops/cn-appraisal-done
 (fn [_ [_ month year _response]]
   {:dispatch [:revops/fetch-cn-appraisals month year]}))

(rf/reg-event-fx
 :revops/finalize-cn-appraisal
 (fn [_ [_ id month year]]
   {:http {:method     :post
           :url        (ep/cn-appraisal-finalize id)
           :body       {}
           :on-success [:revops/fetch-cn-appraisals month year]
           :on-failure [:revops/cn-appraisals-error]}}))

(rf/reg-sub :revops/cn-appraisals (fn [db _] (get-in db [:admin :cn-appraisals] [])))
(rf/reg-sub :revops/cn-appraisals-loading? (fn [db _] (get-in db [:admin :cn-appraisals-loading?])))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- pct [v]
  (when v (-> v js/parseFloat (* 100) (.toFixed 0))))

(defn- mult [v]
  (when v (-> v js/parseFloat (.toFixed 2)
              (str/replace "." ","))))

(defn page []
  (let [filter-s    (r/atom {:month "4" :year "2026"})
        form-inputs (r/atom {})]
    (fn []
      (let [items    @(rf/subscribe [:revops/cn-appraisals])
            loading? @(rf/subscribe [:revops/cn-appraisals-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            total    (reduce + 0 (map #(or (:commission_amount %) 0) (or items [])))
            finals   (count (filter :is_final (or items [])))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "vendas" "apuração CN"]
          :title "Apuração Mensal · CN"
          :subtitle (str (count (or items [])) " consultores · " (:month @filter-s) "/" (:year @filter-s))
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:revops/fetch-cn-appraisals
                                      (:month @filter-s) (:year @filter-s)])}
            [layout/icon "refresh" {:width 14 :height 14}] "Buscar"]
           [:button.btn.btn-primary
            {:on-click (fn []
                         (rf/dispatch [:revops/run-cn-appraisal
                                       {:month  (:month @filter-s)
                                        :year   (:year @filter-s)
                                        :inputs (mapv (fn [[cn-id vals]] (merge {:cn_id cn-id} vals))
                                                       @form-inputs)}]))}
            [layout/icon "target" {:width 14 :height 14}] "Rodar apuração"]]}

         [:div.filter-row {:role "group" :aria-label "Filtrar por período"}
          (for [m (range 1 13)]
            ^{:key m}
            [:button {:type "button"
                      :class (str "chip" (when (= (str m) (:month @filter-s)) " active"))
                      :aria-pressed (str (= (str m) (:month @filter-s)))
                      :aria-label (str "Mês " m)
                      :on-click #(swap! filter-s assoc :month (str m))}
             (str m)])
          [:div {:role "separator" :aria-hidden "true"
                 :style {:width "1px" :height "20px" :background "var(--border-subtle)" :margin "0 4px"}}]
          (for [y ["2025" "2026"]]
            ^{:key y}
            [:button {:type "button"
                      :class (str "chip" (when (= y (:year @filter-s)) " active"))
                      :aria-pressed (str (= y (:year @filter-s)))
                      :on-click #(swap! filter-s assoc :year y)}
             y])]

         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "team" {:width 14 :height 14}] "consultores"]
           [:div.kpi-value (str (count (or items [])))]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "comissão total"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "·")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "check" {:width 14 :height 14}] "finalizados"]
           [:div.kpi-value (str finals " / " (count (or items [])))]]]

         [:div.callout
          [layout/icon "info" {:width 20 :height 20}]
          [:div {:style {:flex 1}}
           [:strong "Como funciona"]
           [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
            "Preencha os valores realizados nos formulários da equipe (em CN · Metas) e clique em Rodar apuração."]]]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "CN"]
             [:th.center "Score"]
             [:th.right "Mult."]
             [:th.right "Comissão"]
             [:th.right "Status"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 5 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? items)
              [:tr [:td {:col-span 5 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma apuração · rode a apuração para gerar"]]

              :else
              (for [row items]
                ^{:key (:id row)}
                [:tr
                 [:td.name (:cn_name row)]
                 [:td.center.num (str (or (pct (:score_final row)) "·") "%")]
                 [:td.right.num (str (or (mult (:multiplicador row)) "·") "x")]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:commission_amount row)) "·"))]
                 [:td.right
                  (if (:is_final row)
                    [:span.badge.badge-paid "Final"]
                    [:button.btn.btn-primary.btn-sm
                     {:on-click #(rf/dispatch [:revops/finalize-cn-appraisal
                                                (:id row) (:month @filter-s) (:year @filter-s)])}
                     "Finalizar"])]]))]]]]))))
