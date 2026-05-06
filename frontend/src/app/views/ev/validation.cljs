(ns app.views.ev.validation
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.auth.subs]))

;; EV · Validação — list of deals to approve / contest, design styling.

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- contest-modal []
  (let [comment (r/atom "")]
    (fn [{:keys [open? on-close on-submit deal-id]}]
      [modal/modal {:open? open? :on-close on-close
                    :title "Contestar negócio" :size :md}
       [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
        [:p {:style {:color "var(--fg-3)" :margin 0 :font-size "13px" :line-height "1.6"}}
         "Descreva o motivo da contestação. Sua mensagem será enviada ao RevOps para análise."]
        [inputs/input
         {:label "Comentário"
          :value @comment
          :placeholder "Ex: O MRR calculado está incorreto porque…"
          :on-change #(reset! comment %)
          :required true}]
        [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
         [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
         [btn/button {:variant :danger
                      :disabled (str/blank? @comment)
                      :on-click #(do (on-submit deal-id @comment)
                                     (reset! comment "")
                                     (on-close))}
          "Contestar"]]]])))

(defn validation-page []
  (rf/dispatch [:ev/fetch-validations])
  (let [contest-open?   (r/atom false)
        contest-deal-id (r/atom nil)
        active-tab      (r/atom :pending)]
    (fn []
      (let [validations @(rf/subscribe [:ev/validations])
            loading?    @(rf/subscribe [:ev/loading?])
            user        @(rf/subscribe [:auth/current-user])
            route       @(rf/subscribe [:current-route-name])
            rows        (or validations [])
            pending     (filter #(= (:status %) "PENDING") rows)
            approved    (filter #(= (:status %) "APPROVED") rows)
            contested   (filter #(= (:status %) "CONTESTED") rows)
            shown (case @active-tab
                    :pending pending
                    :approved approved
                    :contested contested
                    rows)
            total-mrr (reduce + 0 (map #(or (:mrr %) 0) rows))
            total-comm (reduce + 0 (map #(or (:commission_monthly %) 0) rows))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "ev" "validação"]
          :title "Validação"
          :subtitle "Revise e aprove ou conteste os negócios calculados"
          :header-actions
          [[:button.btn.btn-primary
            {:disabled (empty? pending)
             :on-click #(doseq [r pending]
                          (rf/dispatch [:ev/approve-validation (:id r)]))}
            [layout/icon "check" {:width 14 :height 14}] "Aprovar todos"]]}

         ;; KPIs
         [:div.kpi-grid.-three
          [:div.kpi
           [:div.kpi-label [layout/icon "list" {:width 14 :height 14}] "negócios"]
           [:div.kpi-value (str (count rows))]
           [:div.kpi-foot (str (count pending) " pendentes")]]
          [:div.kpi
           [:div.kpi-label [layout/icon "money" {:width 14 :height 14}] "MRR total"]
           [:div.kpi-value [:span.currency "R$"] (fmt-int total-mrr)]]
          [:div.kpi
           [:div.kpi-label [layout/icon "check" {:width 14 :height 14}] "comissão estimada"]
           [:div.kpi-value [:span.currency "R$"] (fmt-int total-comm)]]]

         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "0 24px"}}
           [:div.tabs {:role "tablist" :aria-label "Status da validação"}
            [:button {:type "button"
                      :class (str "tab" (when (= @active-tab :pending) " active"))
                      :role "tab" :aria-selected (str (= @active-tab :pending))
                      :on-click #(reset! active-tab :pending)}
             "Pendentes "
             [:span {:style {:background "var(--warning-lightest)" :color "var(--warning-text)"
                             :font-family "var(--font-mono)" :font-size "11px"
                             :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
              (count pending)]]
            [:button {:type "button"
                      :class (str "tab" (when (= @active-tab :approved) " active"))
                      :role "tab" :aria-selected (str (= @active-tab :approved))
                      :on-click #(reset! active-tab :approved)}
             "Aprovados " [:span {:style {:background "var(--bg-2)" :color "var(--fg-3)"
                                          :font-family "var(--font-mono)" :font-size "11px"
                                          :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
                           (count approved)]]
            [:button {:type "button"
                      :class (str "tab" (when (= @active-tab :contested) " active"))
                      :role "tab" :aria-selected (str (= @active-tab :contested))
                      :on-click #(reset! active-tab :contested)}
             "Contestados " [:span {:style {:background "var(--danger-lightest)" :color "var(--danger-text)"
                                            :font-family "var(--font-mono)" :font-size "11px"
                                            :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
                             (count contested)]]]]
          [:table.table
           [:thead
            [:tr
             [:th "Cliente"]
             [:th "Benefício"]
             [:th.right "MRR"]
             [:th.right "Comissão/mês"]
             [:th "Status"]
             [:th.right "Ações"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 6 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? shown)
              [:tr [:td {:col-span 6 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma validação"]]

              :else
              (for [row shown]
                ^{:key (:id row)}
                [:tr
                 [:td.name (:client_name row)]
                 [:td.muted (or (:benefit_type row) "·")]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:mrr row)) "·"))]
                 [:td.right.strong-num (str "R$ " (or (fmt-int (:commission_monthly row)) "·"))]
                 [:td (case (:status row)
                        "PENDING"   [:span.badge.badge-pending "Pendente"]
                        "APPROVED"  [:span.badge.badge-approved "Aprovado"]
                        "CONTESTED" [:span.badge.badge-contested "Contestado"]
                        [:span.badge.badge-locked (or (:status row) "·")])]
                 [:td.right
                  (when (= (:status row) "PENDING")
                    [:<>
                     [:button.btn.btn-primary.btn-sm
                      {:on-click #(rf/dispatch [:ev/approve-validation (:id row)])}
                      "Aprovar"]
                     " "
                     [:button.btn.btn-danger.btn-sm
                      {:on-click #(do (reset! contest-deal-id (:id row))
                                      (reset! contest-open? true))}
                      "Contestar"]])]]))]]]

         [contest-modal {:open? @contest-open?
                         :on-close #(reset! contest-open? false)
                         :on-submit (fn [id comment]
                                      (rf/dispatch [:ev/contest-validation id comment]))
                         :deal-id @contest-deal-id}]]))))
