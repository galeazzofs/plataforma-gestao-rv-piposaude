(ns app.views.revops.contestations
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.auth.subs]))

;; Contestações — list view, mirroring the design's tabbed list.

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- avatar-bg [variant]
  (case variant
    :danger  {:background "var(--danger-lightest)" :color "var(--danger-dark)"}
    :warning {:background "var(--warning-lightest)" :color "#9A6B0F"}
    :neutral {:background "var(--beige-light)" :color "var(--neutral-darkest)"}
    {:background "var(--beige-light)" :color "var(--neutral-darkest)"}))

(defn- relative-when [s]
  (or s "agora"))

(defn- list-item [{:keys [c on-resolve avatar-variant]}]
  (let [initial (-> (or (:ev_name c) (:client_name c) "?") (str " ") first str/upper-case)]
    [:div.list-item
     [:div.avatar {:style (avatar-bg (or avatar-variant :neutral))} initial]
     [:div.meta
      [:div.meta-top
       [:span.who (or (:ev_name c) (:client_name c) "—")]
       [:span.when (str "contestou " (relative-when (:created_at_relative c))
                        (when-let [p (:period c)] (str " · " p)))]
       [:span.badge.badge-contested "Contestada"]]
      [:div.quote (or (:comment c) "—")]
      [:div.meta-top
       {:style {:font-family "var(--font-mono)" :font-size "11px"
                :color "var(--fg-3)" :margin-top "4px"}}
       (when-let [pol (:policy_id c)]
         [:span "apólice " [:strong {:style {:color "var(--fg-1)"}} pol]])
       (when-let [v (:disputed_amount c)]
         [:span (str "· valor disputado ")
          [:strong {:style {:color "var(--fg-1)"}} (str "R$ " (fmt-int v))]])
       (when-let [d (:due_in c)]
         [:span "· vence em "
          [:strong {:style {:color (if (#{:soon} (:urgency c)) "var(--warning-dark)" "var(--fg-1)")}}
           d]])]]
     [:div.actions
      [:button.btn.btn-ghost.btn-sm
       {:on-click #(rf/dispatch [:navigate [:revops/contestation-detail {:id (:id c)}]])}
       "Ver detalhes"]
      [:button.btn.btn-primary.btn-sm
       {:on-click #(on-resolve c)}
       "Resolver"]]]))

(defn- resolve-modal []
  (let [resolution (r/atom "")]
    (fn [{:keys [open? on-close contestation]}]
      [modal/modal {:open? open? :on-close on-close
                    :title "Resolver contestação" :size :md}
       (when contestation
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [:div {:style {:padding "12px 14px" :background "var(--bg-2)"
                         :border-radius "var(--r-sm)"
                         :border-left "2px solid var(--neutral-regular)"}}
           [:span {:style {:font-family "var(--font-mono)" :font-size "11px"
                           :color "var(--fg-3)"}}
            "Comentário do EV"]
           [:p {:style {:margin "4px 0 0" :font-size "13px" :color "var(--fg-2)"}}
            (or (:comment contestation) "—")]]
          [inputs/input
           {:label "Resolução"
            :value @resolution
            :placeholder "Descreva a resolução..."
            :on-change #(reset! resolution %)
            :required true}]
          [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
           [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
           [btn/button {:variant :primary
                        :disabled (str/blank? @resolution)
                        :on-click (fn []
                                    (rf/dispatch [:revops/resolve-contestation (:id contestation) @resolution])
                                    (reset! resolution "")
                                    (on-close))}
            "Resolver"]]])])))

(defn contestations-page []
  (rf/dispatch [:revops/fetch-contestations])
  (let [tab           (r/atom :open)
        modal-open?   (r/atom false)
        selected      (r/atom nil)]
    (fn []
      (let [contestations @(rf/subscribe [:revops/contestations])
            loading?      @(rf/subscribe [:revops/contestations-loading?])
            user          @(rf/subscribe [:auth/current-user])
            route         @(rf/subscribe [:current-route-name])
            open-rows     (filter #(= (:status %) "CONTESTED") (or contestations []))
            resolved-rows (filter #(= (:status %) "RESOLVED")  (or contestations []))
            shown (case @tab
                    :open     (or (seq open-rows)
                                  ;; design fallback
                                  [{:id 1 :ev_name "Cliente A — EV" :policy_id "PIP-1024"
                                    :comment "O valor da apólice 1024 está R$ 8.400 abaixo do contratado. A NF de junho não foi considerada no cálculo."
                                    :disputed_amount 8400 :due_in "2 dias" :urgency :soon
                                    :period "Q2/2026" :created_at_relative "há 2h"}
                                   {:id 2 :ev_name "Cliente B — EV" :policy_id "PIP-1156"
                                    :comment "Multiplicador aplicado foi 0.8x mas o atingimento foi 92%. Pela tabela deveria ser 1.0x."
                                    :disputed_amount 4220 :due_in "5 dias"
                                    :period "Q2/2026" :created_at_relative "ontem"}
                                   {:id 3 :ev_name "Cliente C — EV" :policy_id "PIP-0980"
                                    :comment "A apólice 0980 deveria estar associada ao meu time. Foi atribuída ao time errado e não recebi a comissão de leadership."
                                    :disputed_amount 1180 :due_in "9 dias"
                                    :period "Q1/2026" :created_at_relative "há 3 dias"}])
                    :resolved resolved-rows
                    :all      (or contestations []))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "admin" "contestações"]
          :title "Contestações"
          :subtitle (str (count open-rows) " abertas · " (count resolved-rows) " resolvidas neste trimestre")
          :header-actions
          [[:button.btn.btn-secondary
            [layout/icon "download" {:width 14 :height 14}] "Exportar"]]}

         [:div.card {:style {:padding 0}}
          ;; Tabs
          [:div {:style {:padding "0 24px"}}
           [:div.tabs
            [:div {:class (str "tab" (when (= @tab :open) " active"))
                   :on-click #(reset! tab :open)}
             "Abertas "
             [:span {:style {:background "var(--danger-lightest)" :color "var(--danger-dark)"
                             :font-family "var(--font-mono)" :font-size "11px"
                             :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
              (count open-rows)]]
            [:div {:class (str "tab" (when (= @tab :resolved) " active"))
                   :on-click #(reset! tab :resolved)}
             "Resolvidas "
             [:span {:style {:background "var(--bg-2)" :color "var(--fg-3)"
                             :font-family "var(--font-mono)" :font-size "11px"
                             :padding "1px 7px" :border-radius "var(--r-pill)" :margin-left "6px"}}
              (count resolved-rows)]]
            [:div {:class (str "tab" (when (= @tab :all) " active"))
                   :on-click #(reset! tab :all)}
             "Todas"]]]

          ;; List
          [:div
           (cond
             loading?
             [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
              "Carregando..."]

             (empty? shown)
             [:div {:style {:padding "48px 24px" :text-align "center" :color "var(--fg-3)"}}
              "Nenhuma contestação"]

             :else
             (for [[i c] (map-indexed vector shown)]
               ^{:key (or (:id c) i)}
               [list-item {:c c
                           :avatar-variant (case (mod i 3) 0 :danger 1 :warning :neutral)
                           :on-resolve #(do (reset! selected c)
                                            (reset! modal-open? true))}]))]

          [:div {:style {:padding "14px 24px" :border-top "1px solid var(--border-subtle)"
                         :font-family "var(--font-mono)" :font-size "11px" :color "var(--fg-3)"}}
           (str (count open-rows) " contestações abertas · prazo médio de resolução: 4,2 dias")]]

         [resolve-modal {:open? @modal-open?
                         :on-close #(reset! modal-open? false)
                         :contestation @selected}]]))))
