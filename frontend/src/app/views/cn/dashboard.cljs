(ns app.views.cn.dashboard
  (:require [clojure.string :as str]
            [reagent.core :as r]
            [re-frame.core :as rf]
            [app.api.endpoints :as ep]
            [app.ds.layout :as layout]
            [app.auth.subs]))

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

(rf/reg-event-fx
 :cn/approve-appraisal
 (fn [_ [_ appraisal-id]]
   {:http {:method     :post
           :url        (ep/cn-appraisal-transition appraisal-id)
           :body       {:to "LIDER_REVIEW"}
           :on-success [:cn/appraisal-action-success]
           :on-failure [:cn/appraisal-action-error]}}))

(rf/reg-event-fx
 :cn/contest-appraisal
 (fn [_ [_ appraisal-id note]]
   {:http {:method     :post
           :url        (ep/cn-appraisal-contest appraisal-id)
           :body       {:note note}
           :on-success [:cn/appraisal-action-success]
           :on-failure [:cn/appraisal-action-error]}}))

(rf/reg-event-fx
 :cn/appraisal-action-success
 (fn [_ _]
   {:dispatch-n [[:cn/fetch-appraisals]
                 [:ui/show-toast {:type :success
                                  :message "Apuracao atualizada"}]]}))

(rf/reg-event-fx
 :cn/appraisal-action-error
 (fn [_ _]
   {:dispatch [:ui/show-toast {:type :error
                               :message "Erro ao atualizar apuracao"}]}))

(rf/reg-sub :cn/appraisals (fn [db _] (get-in db [:cn :appraisals] [])))
(rf/reg-sub :cn/appraisals-loading? (fn [db _] (get-in db [:cn :appraisals-loading?])))

(defn- num [v]
  (cond
    (nil? v) 0
    (number? v) v
    (string? v) (or (js/parseFloat v) 0)
    :else 0))

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (num v)) "pt-BR")))

(defn- pct [v]
  (when v (-> v num (* 100) (.toFixed 0))))

(defn- mult [v]
  (when v (-> v num (.toFixed 2) (str/replace "." ","))))

(defn- status-badge [status final?]
  (cond
    final? [:span.badge.badge-paid "Final"]
    (= status "VALIDATING") [:span.badge.badge-review "Validar"]
    (= status "LIDER_REVIEW") [:span.badge.badge-review "Com lider"]
    (= status "REVOPS_REVIEW") [:span.badge.badge-pending "RevOps"]
    (= status "CALCULATING") [:span.badge.badge-pending "Calculando"]
    :else [:span.badge.badge-locked (or status "Rascunho")]))

(defn- actions-cell [row contest-id contest-note]
  (let [id (:id row)
        validating? (= (:status row) "VALIDATING")
        open? (= @contest-id id)]
    [:td.right
     (cond
       open?
       [:div {:style {:display "grid" :gap "8px" :justify-items "end"}}
        [:textarea.field-input
         {:value @contest-note
          :rows 3
          :style {:min-width "220px" :resize "vertical"}
          :on-change #(reset! contest-note (.. % -target -value))}]
        [:div {:style {:display "flex" :gap "8px"}}
         [:button.btn.btn-ghost.btn-sm
          {:on-click #(do (reset! contest-id nil)
                          (reset! contest-note ""))}
          "Cancelar"]
         [:button.btn.btn-primary.btn-sm
          {:disabled (str/blank? @contest-note)
           :on-click #(do
                        (rf/dispatch [:cn/contest-appraisal id @contest-note])
                        (reset! contest-id nil)
                        (reset! contest-note ""))}
          "Enviar"]]]

       validating?
       [:div {:style {:display "flex" :gap "8px" :justify-content "flex-end"}}
        [:button.btn.btn-ghost.btn-sm
         {:on-click #(do (reset! contest-id id)
                         (reset! contest-note ""))}
         "Contestar"]
        [:button.btn.btn-primary.btn-sm
         {:on-click #(rf/dispatch [:cn/approve-appraisal id])}
         "Aprovar"]]

       :else
       [:span.muted "Sem acao"])]))

(defn page []
  (let [contest-id (r/atom nil)
        contest-note (r/atom "")]
    (rf/dispatch [:cn/fetch-appraisals])
    (fn []
      (let [items    @(rf/subscribe [:cn/appraisals])
            loading? @(rf/subscribe [:cn/appraisals-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            rows     (or items [])
            total    (reduce + 0 (map #(num (:commission_amount %)) rows))
            months   (count rows)
            finals   (count (filter :is_final rows))
            pending  (count (filter #(= (:status %) "VALIDATING") rows))
            avg-pct  (when (seq rows)
                       (-> (/ (reduce + 0 (map #(num (:score_final %)) rows))
                              (count rows))
                           (* 100)))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "cn" "apuracoes"]
          :title "Minhas Apuracoes"
          :subtitle (str months " ciclos, " finals " finalizados")
          :header-actions
          [[:button.btn.btn-secondary
            {:on-click #(rf/dispatch [:navigate :cn/simulator])}
            [layout/icon "target" {:width 14 :height 14}] "Simulador"]]}

         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "total apurado"]
           [:div.kpi-value [:span.currency "R$"] (or (fmt-int total) "0")]
           [:div.kpi-foot (str months " ciclos")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "target" {:width 14 :height 14}] "score medio"]
           [:div.kpi-value (str (or (some-> avg-pct (.toFixed 0)) "0"))
            [:span.frac "%"]]]
          [:div.kpi
           [:div.kpi-label [layout/icon "check" {:width 14 :height 14}] "pendentes CN"]
           [:div.kpi-value (str pending)]
           [:div.kpi-foot (str finals " ciclos finais")]]]

         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "18px 20px 0"}}
           [:h3 "Apuracoes mensais"]
           [:div.card-sub "Score, multiplicador e valor final por mes"]]
          [:table.table
           [:thead
            [:tr
             [:th "Periodo"]
             [:th.center "Score"]
             [:th.right "Multipl."]
             [:th.right "Comissao"]
             [:th "Status"]
             [:th.right "Acoes"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 6 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando..."]]

              (empty? rows)
              [:tr [:td {:col-span 6 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma apuracao disponivel"]]

              :else
              (for [row rows]
                ^{:key (or (:id row) (str (:year row) "-" (:month row)))}
                [:tr
                 [:td.name.num (str (:month row) "/" (:year row))]
                 [:td.center.num (str (or (pct (:score_final row)) "0") "%")]
                 [:td.right.num (str (or (mult (:multiplicador row)) "0,00") "x")]
                 [:td.right.strong-num
                  (str "R$ " (or (fmt-int (:commission_amount row)) "0"))]
                 [:td [status-badge (:status row) (:is_final row)]]
                 [actions-cell row contest-id contest-note]]))]]]]))))
