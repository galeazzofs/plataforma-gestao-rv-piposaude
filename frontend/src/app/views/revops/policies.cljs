(ns app.views.revops.policies
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.views.revops.policy-edit-modal :as edit-modal]
            [app.utils.format :as fmt]
            [app.auth.subs]))

(defn- or-dash [v] (if (or (nil? v) (= v "")) "—" v))

(def benefit-labels
  {"SAUDE" "Saúde" "ODONTO" "Odonto" "VIDA" "Vida"})

(defn- fmt-benefit [v]
  (or (get benefit-labels v) v "—"))

(defn- fmt-date
  "ISO yyyy-mm-dd → dd/mm/yyyy."
  [iso]
  (if (and iso (string? iso) (>= (count iso) 10))
    (let [[y m d] (str/split (subs iso 0 10) #"-")]
      (str d "/" m "/" y))
    "—"))

(defn policies-page []
  (let [filters     (r/atom {:status "" :page 1 :search ""})
        modal-open? (r/atom false)
        selected    (r/atom nil)
        open-edit   (fn [row] (reset! selected row) (reset! modal-open? true))
        close-edit  #(reset! modal-open? false)
        fetch-fn    (fn []
                      (rf/dispatch [:revops/fetch-policies
                                    (-> @filters
                                        (update :status #(when-not (= "" %) %))
                                        (update :search #(when-not (= "" %) %)))]))]
    (rf/dispatch [:revops/fetch-policies @filters])
    (rf/dispatch [:revops/fetch-users])
    (fn []
      (let [policies @(rf/subscribe [:revops/policies])
            meta     @(rf/subscribe [:revops/policies-meta])
            loading? @(rf/subscribe [:revops/policies-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])
            total    (or (:total meta) (count (or policies [])))
            actives       (count (filter #(= (:commission_status %) "PROJECTED") (or policies [])))
            in-validation (count (filter #(= (:commission_status %) "IN_PAYMENT") (or policies [])))
            suspended     (count (filter #(= (:commission_status %) "CANCELLED") (or policies [])))
            operators-count (count (->> policies (map :partner_operator) (filter some?) distinct))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "apólices"]
          :title "Apólices"
          :subtitle (str total " apólice" (when (not= 1 total) "s")
                         (when (pos? operators-count)
                           (str " · " operators-count " operadora"
                                (when (not= 1 operators-count) "s"))))
          :header-actions
          [[:div.search
            [layout/icon "search" {:width 14 :height 14}]
            [:input {:placeholder "Apólice, cliente, EV…"
                     :value (:search @filters)
                     :on-change (fn [e]
                                  (swap! filters assoc :search (.. e -target -value))
                                  (fetch-fn))}]]]}

         ;; Filter chips reflect real counts loaded from the API
         [:div.filter-row
          [:div {:class (str "chip" (when (= "" (:status @filters)) " active"))
                 :on-click #(do (swap! filters assoc :status "") (fetch-fn))}
           (str "Todas (" total ")")]
          [:div {:class (str "chip" (when (= "PROJECTED" (:status @filters)) " active"))
                 :on-click #(do (swap! filters assoc :status "PROJECTED") (fetch-fn))}
           (str "Ativas (" actives ")")]
          [:div {:class (str "chip" (when (= "IN_PAYMENT" (:status @filters)) " active"))
                 :on-click #(do (swap! filters assoc :status "IN_PAYMENT") (fetch-fn))}
           (str "Em pagamento (" in-validation ")")]
          [:div {:class (str "chip" (when (= "CANCELLED" (:status @filters)) " active"))
                 :on-click #(do (swap! filters assoc :status "CANCELLED") (fetch-fn))}
           (str "Canceladas (" suspended ")")]]

         ;; Table — original column set (Apólice / EV / Cliente / Operadora /
         ;; Benefício / Data Gongo / MRR / Comissão Potencial / Total Pago /
         ;; Meses) plus inline edit.
         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "Apólice"]
             [:th "EV"]
             [:th "Cliente"]
             [:th "Operadora"]
             [:th "Benefício"]
             [:th "Data Gongo"]
             [:th.right "MRR"]
             [:th.right "Comissão Potencial"]
             [:th.right "Total Pago"]
             [:th.center "Meses"]
             [:th.right ""]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 11 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? policies)
              [:tr [:td {:col-span 11 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhuma apólice encontrada"]]

              :else
              (for [p policies]
                ^{:key (or (:id p) (:numero_apolice p) (hash p))}
                [:tr
                 [:td.name.num (or-dash (:numero_apolice p))]
                 [:td (or (:ev_name p) "—")]
                 [:td (or (:client_name p) "—")]
                 [:td.muted (or-dash (:partner_operator p))]
                 [:td.muted (fmt-benefit (:benefit_type p))]
                 [:td.num.muted (fmt-date (:closed_date p))]
                 [:td.right.strong-num (or (fmt/fmt-brl-int (:mrr_for_commission p)) "—")]
                 [:td.right.strong-num (or (fmt/fmt-brl-int (:commission_potential p)) "—")]
                 [:td.right.strong-num (or (fmt/fmt-brl-int (:commission_paid_total p)) "—")]
                 [:td.center.num (str (or (:installments_paid p) 0) "/12")]
                 [:td.right
                  [:button.btn.btn-ghost.btn-sm
                   {:on-click #(open-edit p)
                    :title "Editar"}
                   [layout/icon "edit" {:width 12 :height 12}]]]]))]]
          (when (and (some? meta) (> (or (:total_pages meta) 1) 1))
            [:div {:style {:padding "12px 20px" :border-top "1px solid var(--border-subtle)"
                           :display "flex" :justify-content "space-between" :align-items "center"
                           :font-family "var(--font-mono)" :font-size "11px" :color "var(--fg-3)"}}
             [:span (str "Página " (or (:page meta) 1) " de " (or (:total_pages meta) 1))]
             [:div {:style {:display "flex" :gap "8px"}}
              [:button.btn.btn-secondary.btn-sm
               {:disabled (<= (or (:page meta) 1) 1)
                :on-click #(do (swap! filters update :page (fnil dec 1)) (fetch-fn))}
               "‹ Anterior"]
              [:button.btn.btn-secondary.btn-sm
               {:disabled (>= (or (:page meta) 1) (or (:total_pages meta) 1))
                :on-click #(do (swap! filters update :page (fnil inc 1)) (fetch-fn))}
               "Próxima ›"]]])]

         [edit-modal/policy-edit-modal
          {:open? @modal-open?
           :policy @selected
           :on-close close-edit}]]))))
